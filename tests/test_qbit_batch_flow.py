"""Exercise the qBittorrent batch loop with a fake qBittorrent API."""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest


class FakeLock:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


class FakeTorrentFile:
    def __init__(self, index, name, size, priority=1):
        self.index = index
        self.name = name
        self.size = size
        self.progress = 1.0
        self.priority = priority


class FakeTorrents:
    def __init__(self, tor_info, files):
        self.tor_info = tor_info
        self.file_list = files
        self.priority_calls = []
        self.started = 0
        self.stopped = 0
        self.deleted = False

    async def info(self, hashes=None, tag=None):
        return [self.tor_info]

    async def files(self, tor_hash):
        return self.file_list

    async def file_prio(self, hash, id, priority):
        self.priority_calls.append((list(id), priority))
        for file_info in self.file_list:
            if file_info.index in id:
                file_info.priority = priority

    async def stop(self, hashes):
        self.stopped += 1

    async def start(self, hashes):
        self.started += 1

    async def delete(self, hashes, delete_files):
        self.deleted = True

    async def delete_tags(self, tags):
        pass


def _load_batch_module(monkeypatch, tmp_path, tor_info, files):
    modules = {}

    def stub(name, **attrs):
        module = ModuleType(name)
        for key, value in attrs.items():
            setattr(module, key, value)
        monkeypatch.setitem(sys.modules, name, module)
        modules[name] = module
        return module

    async def noop(*args, **kwargs):
        return None

    async def async_sync_to_async(func, *args, **kwargs):
        return func(*args, **kwargs)

    # ``tests/run_test.py`` replaces ``aiofiles.os`` with a two-function stub,
    # so provide the full async surface this module needs.
    aiofiles_os = ModuleType("aiofiles.os")

    async def aio_makedirs(path, **kwargs):
        os.makedirs(path, exist_ok=kwargs.get("exist_ok", False))

    async def aio_remove(path):
        os.remove(path)

    async def aio_rename(source, destination):
        os.rename(source, destination)

    async def aio_rmdir(path):
        os.rmdir(path)

    aiofiles_os.makedirs = aio_makedirs
    aiofiles_os.remove = aio_remove
    aiofiles_os.rename = aio_rename
    aiofiles_os.rmdir = aio_rmdir
    aiofiles_os.path = SimpleNamespace(
        exists=lambda path: _async_bool(os.path.exists(path)),
        isfile=lambda path: _async_bool(os.path.isfile(path)),
        isdir=lambda path: _async_bool(os.path.isdir(path)),
    )
    monkeypatch.setitem(sys.modules, "aiofiles.os", aiofiles_os)

    stub(
        "bot",
        DOWNLOAD_DIR=str(tmp_path),
        LOGGER=SimpleNamespace(info=lambda *a, **k: None, error=lambda *a, **k: None),
        bot_loop=SimpleNamespace(create_task=lambda coro: coro),
        intervals={"stopAll": False},
        non_queued_dl=set(),
        qb_listener_lock=FakeLock(),
        qb_torrents={},
        queue_dict_lock=FakeLock(),
        task_dict={},
        task_dict_lock=FakeLock(),
    )
    stub("bot.core")
    stub(
        "bot.core.torrent_manager",
        TorrentManager=SimpleNamespace(
            qbittorrent=SimpleNamespace(torrents=FakeTorrents(tor_info, files))
        ),
    )
    stub("bot.helper")
    stub("bot.helper.ext_utils", __path__=[])
    stub("bot.helper.listeners", __path__=[])
    stub("bot.helper.mirror_leech_utils", __path__=[])
    stub("bot.helper.mirror_leech_utils.gdrive_utils", __path__=[])
    stub("bot.helper.mirror_leech_utils.rclone_utils", __path__=[])
    stub("bot.helper.mirror_leech_utils.status_utils", __path__=[])
    stub("bot.helper.mirror_leech_utils.upload_utils", __path__=[])
    stub("bot.helper.telegram_helper", __path__=[])

    file_types_path = (
        Path(__file__).resolve().parent.parent
        / "bot"
        / "helper"
        / "ext_utils"
        / "file_types.py"
    )
    spec = importlib.util.spec_from_file_location(
        "bot.helper.ext_utils.file_types", file_types_path
    )
    file_types = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(file_types)
    monkeypatch.setitem(sys.modules, "bot.helper.ext_utils.file_types", file_types)

    stub("bot.helper.ext_utils.bot_utils", sync_to_async=async_sync_to_async)
    stub(
        "bot.helper.ext_utils.files_utils",
        clean_download=noop,
        split_file=noop,
    )
    stub("bot.helper.ext_utils.links_utils", is_gdrive_id=lambda value: False)
    stub(
        "bot.helper.ext_utils.status_utils",
        get_readable_file_size=lambda size: f"{size} B",
    )
    stub("bot.helper.ext_utils.task_manager", start_from_queued=noop)
    stub(
        "bot.helper.telegram_helper.message_utils",
        send_message=noop,
        update_status_message=noop,
    )

    class DummyUploader:
        def __init__(self, listener, path):
            self.listener = listener
            self.path = path

        async def upload(self):
            return None

    class DummyStatus:
        def __init__(self, listener, obj, gid, status):
            self.listener = listener
            self.obj = obj

    stub(
        "bot.helper.mirror_leech_utils.gdrive_utils.upload",
        GoogleDriveUpload=DummyUploader,
    )
    stub(
        "bot.helper.mirror_leech_utils.rclone_utils.transfer",
        RcloneTransferHelper=DummyUploader,
    )
    stub(
        "bot.helper.mirror_leech_utils.upload_utils.telegram_uploader",
        TelegramUploader=DummyUploader,
    )
    stub(
        "bot.helper.mirror_leech_utils.upload_utils.gofile_uploader",
        GoFileUploader=DummyUploader,
    )
    stub(
        "bot.helper.mirror_leech_utils.upload_utils.buzzheavier_uploader",
        BuzzHeavierUploader=DummyUploader,
    )
    for status_name, class_name in [
        ("gdrive_status", "GoogleDriveStatus"),
        ("rclone_status", "RcloneStatus"),
        ("telegram_status", "TelegramStatus"),
        ("gofile_status", "GoFileStatus"),
        ("buzzheavier_status", "BuzzHeavierStatus"),
        ("qbit_status", "QbittorrentStatus"),
    ]:
        stub(
            f"bot.helper.mirror_leech_utils.status_utils.{status_name}",
            **{class_name: DummyStatus},
        )

    module_path = (
        Path(__file__).resolve().parent.parent
        / "bot"
        / "helper"
        / "listeners"
        / "qbit_batch.py"
    )
    spec = importlib.util.spec_from_file_location(
        "bot.helper.listeners.qbit_batch", module_path
    )
    module = importlib.util.module_from_spec(spec)
    module.__package__ = "bot.helper.listeners"
    monkeypatch.setitem(sys.modules, "bot.helper.listeners.qbit_batch", module)
    spec.loader.exec_module(module)
    return module


async def _async_bool(value):
    return value


def _listener(tmp_path):
    task_dir = tmp_path / "123"
    task_dir.mkdir(exist_ok=True)
    uploads = []
    errors = []
    completed = []

    async def on_upload_complete(*args, **kwargs):
        completed.append((args, kwargs))

    async def on_download_error(error, button=None):
        errors.append(error)

    listener = SimpleNamespace(
        mid=123,
        dir=f"{task_dir}/",
        name="TorrentName",
        size=0,
        is_file=False,
        up_dest="",
        is_leech=True,
        is_buzzheavier=False,
        is_gofile=False,
        is_cancelled=False,
        files_per_batch=1,
        batch_max_size=0,
        file_types=[],
        included_extensions=[],
        excluded_extensions=[],
        split_size=0,
        batch_current=0,
        batch_total=0,
        message=SimpleNamespace(chat=SimpleNamespace(id=555)),
        on_upload_complete=on_upload_complete,
        on_download_error=on_download_error,
    )
    return listener, task_dir, uploads, errors, completed


@pytest.mark.asyncio
async def test_batch_downloads_uploads_and_deletes_in_order(monkeypatch, tmp_path):
    root = tmp_path / "123" / "TorrentName"
    root.mkdir(parents=True)
    (root / "a.mkv").write_bytes(b"a")
    (root / "b.jpg").write_bytes(b"b")
    tor_info = SimpleNamespace(
        hash="abc123def456", content_path=str(root), state="uploading"
    )
    files = [
        FakeTorrentFile(0, "TorrentName/a.mkv", 1),
        FakeTorrentFile(1, "TorrentName/b.jpg", 1),
    ]
    module = _load_batch_module(monkeypatch, tmp_path, tor_info, files)
    listener, task_dir, uploads, errors, completed = _listener(tmp_path)
    batch = module.QbitBatch(listener, tor_info, files)
    priorities_before_upload = []

    async def fake_upload(job):
        priorities_before_upload.append([file_info.priority for file_info in files])
        uploads.append(job.name)
        job.result = ((None, {f"link-{job.name}": job.name}, 1, 0), {})

    batch._upload_one = fake_upload
    await batch.run()

    assert uploads == ["a.mkv", "b.jpg"]
    assert not (root / "a.mkv").exists()
    assert not (root / "b.jpg").exists()
    assert errors == []
    assert completed  # final summary was sent
    assert batch.uploaded_count == 2


@pytest.mark.asyncio
async def test_batch_skips_unwanted_file_types(monkeypatch, tmp_path):
    root = tmp_path / "123" / "TorrentName"
    root.mkdir(parents=True)
    (root / "a.mkv").write_bytes(b"a")
    tor_info = SimpleNamespace(
        hash="abc123def456", content_path=str(root), state="uploading"
    )
    files = [
        FakeTorrentFile(0, "TorrentName/a.mkv", 1),
        FakeTorrentFile(1, "TorrentName/b.jpg", 1),
    ]
    module = _load_batch_module(monkeypatch, tmp_path, tor_info, files)
    listener, task_dir, uploads, errors, completed = _listener(tmp_path)
    listener.file_types = ["video"]
    batch = module.QbitBatch(listener, tor_info, files)
    assert [file_info["name"] for file_info in batch.pending] == [
        "TorrentName/a.mkv"
    ]
