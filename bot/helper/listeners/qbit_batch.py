"""Download a torrent in file batches, upload each batch, then free the disk.

The torrent stays in qBittorrent for the whole run.  Only the files in the
current batch have priority 1; every other file has priority 0.  When a batch
is complete its files are uploaded one by one with the normal uploader for the
task, then deleted locally before the next files are marked for download.
"""

from asyncio import gather, sleep
from html import escape
from os import path as ospath, symlink
from time import time

from aiofiles.os import makedirs, remove, rename, rmdir
from aiofiles.os import path as aiopath
from psutil import disk_usage

from ... import (
    DOWNLOAD_DIR,
    LOGGER,
    bot_loop,
    intervals,
    non_queued_dl,
    qb_listener_lock,
    qb_torrents,
    queue_dict_lock,
    task_dict,
    task_dict_lock,
)
from ...core.torrent_manager import TorrentManager
from ..ext_utils.bot_utils import sync_to_async
from ..ext_utils.file_types import (
    is_extension_allowed,
    is_file_type_allowed,
    plan_batch,
)
from ..ext_utils.files_utils import clean_download, split_file
from ..ext_utils.links_utils import is_gdrive_id
from ..ext_utils.media_utils import FFMpeg, get_document_type
from ..ext_utils.status_utils import get_readable_file_size
from ..ext_utils.task_manager import start_from_queued
from ..mirror_leech_utils.gdrive_utils.upload import GoogleDriveUpload
from ..mirror_leech_utils.rclone_utils.transfer import RcloneTransferHelper
from ..mirror_leech_utils.status_utils.buzzheavier_status import BuzzHeavierStatus
from ..mirror_leech_utils.status_utils.gdrive_status import GoogleDriveStatus
from ..mirror_leech_utils.status_utils.gofile_status import GoFileStatus
from ..mirror_leech_utils.status_utils.qbit_status import QbittorrentStatus
from ..mirror_leech_utils.status_utils.rclone_status import RcloneStatus
from ..mirror_leech_utils.status_utils.telegram_status import TelegramStatus
from ..mirror_leech_utils.upload_utils.buzzheavier_uploader import BuzzHeavierUploader
from ..mirror_leech_utils.upload_utils.gofile_uploader import GoFileUploader
from ..mirror_leech_utils.upload_utils.telegram_uploader import TelegramUploader
from ..telegram_helper.message_utils import send_message, update_status_message

qb_batches = {}
FREE_SPACE_MARGIN = 256 * 1024 * 1024
METADATA_TIMEOUT = 300


class BatchError(Exception):
    pass


class BatchFileJob:
    """Per-file listener proxy used with the normal uploader classes."""

    def __init__(self, listener, file_info, file_path, rel_dir=""):
        object.__setattr__(self, "_parent", listener)
        object.__setattr__(self, "_up_dest", listener.up_dest)
        self.file_info = file_info
        self.path = file_path
        self.rel_dir = rel_dir
        self.name = ospath.basename(file_info["name"])
        self.size = file_info["size"]
        self.is_file = True
        self.dir = listener.dir
        self.up_dir = ""
        self.result = None
        self.error = ""

    def __getattr__(self, item):
        return getattr(self._parent, item)

    @property
    def is_cancelled(self):
        return self._parent.is_cancelled

    @is_cancelled.setter
    def is_cancelled(self, value):
        self._parent.is_cancelled = value

    @property
    def up_dest(self):
        return self._up_dest

    @up_dest.setter
    def up_dest(self, value):
        self._up_dest = value

    async def on_upload_complete(self, *args, **kwargs):
        self.result = (args, kwargs)

    async def on_upload_error(self, error, button=None):
        self.error = str(error)


class QbitBatch:
    def __init__(self, listener, tor_info, files):
        self.listener = listener
        self.hash = tor_info.hash
        self.tag = f"{listener.mid}"
        self.task_root = listener.dir.rstrip("/")
        self.files = self._file_entries(files)
        self.pending = [
            file_info
            for file_info in self.files
            if file_info["size"]
            and is_extension_allowed(
                file_info["name"],
                listener.included_extensions,
                listener.excluded_extensions,
            )
            and is_file_type_allowed(file_info["name"], listener.file_types)
        ]
        self.done = set()
        self.links = {}
        self.rclone_destination = ""
        self.dir_id = ""
        self.uploaded_count = 0
        self.uploaded_size = 0
        self.seq = 0
        self.batch_offset = 0
        self.error = ""
        # qBittorrent file names already include the torrent's root folder, so
        # they are relative to the task save path, not to content_path.
        self.root = self.task_root
        self.content_path = (tor_info.content_path or "").rstrip("/")
        if not (
            listener.is_leech
            or listener.is_buzzheavier
            or listener.is_gofile
            or is_gdrive_id(listener.up_dest)
        ):
            destination = listener.up_dest
            if destination.startswith("mt:"):
                destination = destination.split("mt:", 1)[1]
            self.rclone_destination = destination

    @staticmethod
    def _file_entries(files):
        entries = []
        for file_info in files:
            entries.append(
                {
                    "index": int(file_info.index),
                    "name": str(file_info.name),
                    "size": int(file_info.size or 0),
                }
            )
        return entries

    async def run(self):
        try:
            LOGGER.info(
                f"Qbit batch start: save_path={self.task_root} "
                f"content_path={self.content_path}"
            )
            if not self.pending:
                raise BatchError(
                    "No downloadable files in this torrent. Check the selected "
                    "file types and included/excluded extensions."
                )
            self.listener.batch_total = len(self.pending)
            self.listener.batch_current = 1
            await self._release_download_queue()
            await self._announce()
            while self.pending:
                if self.listener.is_cancelled or intervals["stopAll"]:
                    await self._abort("")
                    return
                batch = self._next_batch()
                if not batch:
                    break
                self._check_space(batch)
                await self._apply_batch(batch)
                if not await self._wait_batch(batch):
                    await self._abort("Batch download stopped before completion!")
                    return
                if self.listener.is_cancelled or intervals["stopAll"]:
                    await self._abort("")
                    return
                await self._upload_batch(batch)
                if self.listener.is_cancelled or intervals["stopAll"]:
                    await self._abort("")
                    return
                if self.error:
                    await self._abort(self.error)
                    return
                for file_info in batch:
                    if file_info in self.pending:
                        self.pending.remove(file_info)
                    self.done.add(file_info["index"])
            await self._finish()
        except BatchError as error:
            await self._abort(str(error))
        except Exception as error:
            LOGGER.error(f"Qbit batch error: {error}")
            await self._abort(str(error))
        finally:
            qb_batches.pop(self.listener.mid, None)

    async def _announce(self):
        limit = f"{self.listener.files_per_batch} file(s) per batch"
        if self.listener.batch_max_size:
            limit += f", up to {get_readable_file_size(self.listener.batch_max_size)}"
        types = ", ".join(self.listener.file_types)
        text = (
            f"<b>Batch download started:</b> {limit}.\n"
            f"<b>Files queued:</b> {len(self.pending)}"
        )
        if types:
            text += f"\n<b>File types:</b> {escape(types)}"
        await send_message(self.listener.message, text)

    async def _release_download_queue(self):
        async with queue_dict_lock:
            non_queued_dl.discard(self.listener.mid)
        await start_from_queued()

    def _next_batch(self):
        return plan_batch(
            self.pending,
            self.listener.files_per_batch,
            self.listener.batch_max_size,
        )

    def _check_space(self, batch):
        needed = sum(file_info["size"] for file_info in batch)
        free = disk_usage(DOWNLOAD_DIR).free
        if needed > max(0, free - FREE_SPACE_MARGIN):
            raise BatchError(
                "Not enough free space for the next batch: "
                f"need {get_readable_file_size(needed)}, "
                f"free {get_readable_file_size(free)}."
            )

    async def _apply_batch(self, batch):
        batch_indices = [file_info["index"] for file_info in batch]
        try:
            await TorrentManager.qbittorrent.torrents.stop([self.hash])
            await self._set_priorities(batch_indices)
            await TorrentManager.qbittorrent.torrents.start([self.hash])
        except Exception as error:
            raise BatchError(f"Could not start the next batch: {error}") from error
        self.batch_offset = len(self.done)
        self.listener.batch_current = self.batch_offset + 1
        await update_status_message(self.listener.message.chat.id)

    async def _set_priorities(self, batch_indices):
        wanted = set(batch_indices)
        for _ in range(6):
            files = await TorrentManager.qbittorrent.torrents.files(self.hash)
            all_indices = [file_info.index for file_info in files]
            selected = {
                file_info.index for file_info in files if file_info.priority != 0
            }
            if selected == wanted:
                return
            skipped = [index for index in all_indices if index not in wanted]
            if skipped:
                await TorrentManager.qbittorrent.torrents.file_prio(
                    hash=self.hash, id=skipped, priority=0
                )
            await TorrentManager.qbittorrent.torrents.file_prio(
                hash=self.hash, id=batch_indices, priority=1
            )
            await sleep(0.5)
        raise BatchError("qBittorrent did not apply the file priorities.")

    async def _wait_batch(self, batch):
        stopped_time = 0
        while True:
            if self.listener.is_cancelled or intervals["stopAll"]:
                return False
            try:
                infos = await TorrentManager.qbittorrent.torrents.info(
                    hashes=[self.hash]
                )
                if not infos:
                    return False
                torrent = infos[0]
                if torrent.state == "error":
                    return False
                if torrent.state in ("stoppedDL", "pausedDL", "queuedDL"):
                    stopped_time += 3
                    if stopped_time >= 60:
                        return False
                else:
                    stopped_time = 0
                files = await TorrentManager.qbittorrent.torrents.files(self.hash)
            except Exception as error:
                LOGGER.error(f"Qbit batch status error: {error}")
                await sleep(3)
                continue
            progress = {file_info.index: file_info.progress for file_info in files}
            # qBittorrent pre-allocates every selected file and this image turns
            # off the ".!qB" marker, so a file exists long before it is complete.
            # Only the per-file progress proves the data is on disk.
            if all(
                not file_info["size"]
                or progress.get(file_info["index"], 0) >= 0.999
                for file_info in batch
            ):
                return True
            await sleep(3)

    def _candidate_paths(self, file_info):
        name = file_info["name"]
        candidates = [ospath.join(self.task_root, name)]
        if self.content_path:
            root_name = ospath.basename(self.content_path)
            candidates.append(ospath.join(self.content_path, name))
            if name.startswith(f"{root_name}/"):
                candidates.append(
                    ospath.join(self.content_path, name[len(root_name) + 1 :])
                )
            candidates.append(ospath.join(ospath.dirname(self.content_path), name))
        unique = []
        for path in candidates:
            if path not in unique:
                unique.append(path)
        return unique

    async def _resolve_file_path(self, file_info):
        for path in self._candidate_paths(file_info):
            if await aiopath.exists(path):
                return path
        return None

    async def _upload_batch(self, batch):
        try:
            await TorrentManager.qbittorrent.torrents.stop([self.hash])
            await TorrentManager.qbittorrent.torrents.file_prio(
                hash=self.hash,
                id=[file_info["index"] for file_info in batch],
                priority=0,
            )
        except Exception as error:
            LOGGER.error(f"Qbit batch stop before upload: {error}")
        for position, file_info in enumerate(batch, start=1):
            if self.listener.is_cancelled or intervals["stopAll"]:
                return
            path = await self._resolve_file_path(file_info)
            if path is None:
                candidates = ", ".join(self._candidate_paths(file_info))
                self.error = (
                    "Downloaded file is missing. Tried: " + candidates
                )
                return
            rel_dir = ospath.dirname(file_info["name"])
            job = BatchFileJob(self.listener, file_info, path, rel_dir)
            self.listener.batch_current = self.batch_offset + position
            await self._upload_one(job)
            if job.error:
                self.error = job.error
                return
            self._record_result(job)
            await self._delete_local(path)
            self.uploaded_count += 1
            self.uploaded_size += file_info["size"]
            await self._restore_status()
        await self._restore_status()

    async def _upload_one(self, job):
        gid = self.hash[:12]
        chat_id = self.listener.message.chat.id
        if self.listener.is_leech:
            staging = ospath.join(
                self.task_root, f"batch-{self.listener.mid}-{self.seq}"
            )
            self.seq += 1
            await makedirs(staging, exist_ok=True)
            staged_path = ospath.join(staging, job.name)
            original_path = job.path
            moved = False
            try:
                try:
                    await sync_to_async(symlink, job.path, staged_path)
                except OSError:
                    await rename(job.path, staged_path)
                    job.path = staged_path
                    moved = True
                if self.listener.split_size and job.size > self.listener.split_size:
                    free = disk_usage(DOWNLOAD_DIR).free
                    if job.size > max(0, free - FREE_SPACE_MARGIN):
                        job.error = (
                            "Not enough free space to split this file for Telegram: "
                            f"need {get_readable_file_size(job.size)}, "
                            f"free {get_readable_file_size(free)}. Use rclone instead."
                        )
                        return job.error
                    if not await self._split_for_telegram(job, staged_path):
                        job.error = f"Could not split {job.name} for Telegram."
                        return job.error
                    if moved:
                        await rename(staged_path, original_path)
                        moved = False
                    else:
                        await remove(staged_path)
                uploader = TelegramUploader(job, staging)
                async with task_dict_lock:
                    task_dict[self.listener.mid] = TelegramStatus(
                        job, uploader, gid, "up"
                    )
                await gather(update_status_message(chat_id), uploader.upload())
            finally:
                if moved and job.error and await aiopath.exists(staged_path):
                    await rename(staged_path, original_path)
                await clean_download(staging)
        elif self.listener.is_buzzheavier:
            uploader = BuzzHeavierUploader(job, job.path)
            async with task_dict_lock:
                task_dict[self.listener.mid] = BuzzHeavierStatus(
                    job, uploader, gid, "up"
                )
            await gather(update_status_message(chat_id), uploader.upload())
        elif self.listener.is_gofile:
            uploader = GoFileUploader(job, job.path)
            async with task_dict_lock:
                task_dict[self.listener.mid] = GoFileStatus(job, uploader, gid, "up")
            await gather(update_status_message(chat_id), uploader.upload())
        elif is_gdrive_id(self.listener.up_dest):
            uploader = GoogleDriveUpload(job, job.path)
            async with task_dict_lock:
                task_dict[self.listener.mid] = GoogleDriveStatus(
                    job, uploader, gid, "up"
                )
            await gather(update_status_message(chat_id), sync_to_async(uploader.upload))
        else:
            job.up_dest = self._rclone_file_destination(job.rel_dir)
            uploader = RcloneTransferHelper(job)
            async with task_dict_lock:
                task_dict[self.listener.mid] = RcloneStatus(job, uploader, gid, "up")
            await gather(update_status_message(chat_id), uploader.upload(job.path))

    async def _split_for_telegram(self, job, file_path):
        split_size = self.listener.split_size
        parts = -(-job.size // split_size)
        if self.listener.equal_splits:
            split_size = (job.size // parts) + (job.size % parts)
        if not self.listener.as_doc and (await get_document_type(file_path))[0]:
            return await FFMpeg(self.listener).split(
                file_path, job.name, parts, split_size
            )
        return await split_file(file_path, split_size, self.listener)

    def _rclone_file_destination(self, rel_dir):
        if not rel_dir or rel_dir == ".":
            return self.listener.up_dest
        return f"{self.listener.up_dest.rstrip('/')}/{rel_dir}"

    async def _restore_status(self):
        async with task_dict_lock:
            if self.listener.mid in task_dict:
                task_dict[self.listener.mid] = QbittorrentStatus(self.listener)
        await update_status_message(self.listener.message.chat.id)

    async def _delete_local(self, path):
        for file_path in (path, f"{path}.!qB"):
            if await aiopath.exists(file_path):
                try:
                    await remove(file_path)
                except OSError as error:
                    LOGGER.error(f"Could not remove {file_path}: {error}")
        parent = ospath.dirname(path)
        root = self.root.rstrip("/")
        while root and parent.startswith(f"{root}/"):
            try:
                await rmdir(parent)
            except OSError:
                break
            parent = ospath.dirname(parent)

    def _record_result(self, job):
        if not job.result:
            return
        args, kwargs = job.result
        link = args[0] if args else ""
        if self.listener.is_leech or self.listener.is_gofile:
            links = args[1] if len(args) > 1 and isinstance(args[1], dict) else {}
            for file_link, file_name in links.items():
                self.links[file_link] = file_name
            if link:
                self.links.setdefault(link, job.name)
        elif is_gdrive_id(self.listener.up_dest):
            if link:
                self.links.setdefault(link, job.name)
            self.dir_id = self.dir_id or kwargs.get("dir_id", "")
        else:
            if link:
                self.links.setdefault(link, job.name)

    async def _finish(self):
        await self._remove_torrent()
        self.listener.size = self.uploaded_size
        self.listener.is_file = False
        link = next(iter(self.links), "")
        LOGGER.info(
            f"Qbit batch finished: {self.listener.name} - "
            f"{self.uploaded_count} file(s), "
            f"{get_readable_file_size(self.uploaded_size)}"
        )
        if self.listener.is_leech:
            await self.listener.on_upload_complete(
                None, self.links, self.uploaded_count, 0
            )
        else:
            await self.listener.on_upload_complete(
                link,
                self.uploaded_count,
                0,
                "File",
                rclone_path=self.rclone_destination,
                dir_id=self.dir_id,
            )

    async def _remove_torrent(self):
        await remove_qbit_torrent(self.hash, self.tag)

    async def _abort(self, error):
        if error:
            LOGGER.error(f"Qbit batch aborted: {error}")
        await self._remove_torrent()
        await clean_download(self.listener.dir)
        await self._release_download_queue()
        cancelled = self.listener.is_cancelled or intervals["stopAll"]
        if cancelled:
            async with task_dict_lock:
                task_dict.pop(self.listener.mid, None)
            await update_status_message(self.listener.message.chat.id)
            return
        async with task_dict_lock:
            active = self.listener.mid in task_dict
        if active:
            await self.listener.on_download_error(error or "Batch download failed!")


async def wait_for_torrent_files(listener, tor_hash):
    started = time()
    while True:
        if listener.is_cancelled:
            return None, None
        try:
            infos = await TorrentManager.qbittorrent.torrents.info(hashes=[tor_hash])
            if infos:
                torrent = infos[0]
                if torrent.state not in ("metaDL", "checkingResumeData"):
                    files = await TorrentManager.qbittorrent.torrents.files(tor_hash)
                    if files:
                        return torrent, files
        except Exception as error:
            LOGGER.error(f"Waiting for torrent files: {error}")
        if time() - started >= METADATA_TIMEOUT:
            return None, None
        await sleep(1)


async def prepare_qbit_selection(listener, tor_hash):
    """Apply the file-type filter or hand the torrent to the batch runner."""
    try:
        await TorrentManager.qbittorrent.torrents.start([tor_hash])
    except Exception:
        pass
    tor_info, files = await wait_for_torrent_files(listener, tor_hash)
    if tor_info is None or files is None:
        if not listener.is_cancelled:
            await remove_qbit_torrent(tor_hash, f"{listener.mid}")
            await clean_download(listener.dir)
            await listener.on_download_error(
                "Could not read the torrent file list. Metadata may be unavailable."
            )
        return False
    if listener.batch_mode:
        start_qbit_batch(listener, tor_info, files)
        return True
    await apply_file_type_filter(listener, tor_info, files)
    return True


def start_qbit_batch(listener, tor_info, files):
    batch = QbitBatch(listener, tor_info, files)
    qb_batches[listener.mid] = batch
    bot_loop.create_task(batch.run())
    return batch


async def apply_file_type_filter(listener, tor_info, files):
    allowed = [
        file_info
        for file_info in files
        if is_file_type_allowed(file_info.name, listener.file_types)
    ]
    if not allowed:
        await remove_qbit_torrent(tor_info.hash, f"{listener.mid}")
        await listener.on_download_error(
            "No files in this torrent match the selected file types."
        )
        return
    try:
        await TorrentManager.qbittorrent.torrents.stop([tor_info.hash])
        all_indices = [file_info.index for file_info in files]
        await TorrentManager.qbittorrent.torrents.file_prio(
            hash=tor_info.hash, id=all_indices, priority=0
        )
        await TorrentManager.qbittorrent.torrents.file_prio(
            hash=tor_info.hash,
            id=[file_info.index for file_info in allowed],
            priority=1,
        )
        await sleep(0.5)
        await TorrentManager.qbittorrent.torrents.start([tor_info.hash])
    except Exception as error:
        await remove_qbit_torrent(tor_info.hash, f"{listener.mid}")
        await clean_download(listener.dir)
        await listener.on_download_error(
            f"Could not apply the file type filter: {error}"
        )
        return
    listener.batch_total = len(allowed)
    await send_message(
        listener.message,
        f"<b>File type filter:</b> {escape(', '.join(listener.file_types))}. "
        f"{len(allowed)}/{len(files)} file(s) selected.",
    )


async def remove_qbit_torrent(tor_hash, tag):
    try:
        await TorrentManager.qbittorrent.torrents.stop([tor_hash])
    except Exception:
        pass
    try:
        await TorrentManager.qbittorrent.torrents.delete([tor_hash], True)
    except Exception as error:
        LOGGER.error(f"Could not remove torrent {tor_hash}: {error}")
    try:
        await TorrentManager.qbittorrent.torrents.delete_tags([tag])
    except Exception:
        pass
    async with qb_listener_lock:
        qb_torrents.pop(tag, None)
