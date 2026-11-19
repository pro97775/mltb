from sys import executable
from datetime import datetime
from aiofiles import open as aiopen
from aiofiles.os import path as aiopath, remove
from asyncio import gather, create_subprocess_exec
from os import execl as osexecl

from .. import intervals, scheduler, LOGGER
from ..helper.ext_utils.bot_utils import new_task, resolve_command
from ..helper.telegram_helper.message_utils import (
    send_message,
    delete_message,
)
from ..helper.ext_utils.db_handler import database
from ..helper.ext_utils.files_utils import clean_all
from ..helper.telegram_helper.button_build import ButtonMaker
from ..core.telegram_manager import TgClient
from ..core.config_manager import Config, BinConfig
from ..core.torrent_manager import TorrentManager


@new_task
async def restart_bot(_, message):
    buttons = ButtonMaker()
    buttons.data_button("Yes!", "botrestart confirm")
    buttons.data_button("Cancel", "botrestart cancel")
    button = buttons.build_menu(2)
    await send_message(message, "Are you sure you want to restart the bot ?!", button)


def _restart_header(now, is_restart_chat=False):
    title = "Restarted Successfully!" if is_restart_chat else "Bot Restarted!"
    return (
        f"⌬ <b><i>{title}</i></b>\n"
        f"┟ <b>Date:</b> {now.strftime('%d/%m/%y')}\n"
        f"┠ <b>Time:</b> {now.strftime('%I:%M:%S %p')}\n"
        f"┠ <b>Branch:</b> {Config.UPSTREAM_BRANCH}"
    )


async def _send_msg(cid, msg):
    try:
        await TgClient.bot.send_message(
            chat_id=cid,
            text=msg,
            disable_web_page_preview=True,
            disable_notification=True,
        )
    except Exception as e:
        LOGGER.error(e)


async def restart_notification():
    if await aiopath.isfile(".restartmsg"):
        with open(".restartmsg") as f:
            chat_id, msg_id = map(int, f)
    else:
        chat_id, msg_id = 0, 0

    now = datetime.now()

    if Config.DATABASE_URL and (Config.INC_TASK_NOTIFY or Config.INC_TASK_RESUME):
        if notifier_dict := await database.get_incomplete_tasks():
            if Config.INC_TASK_RESUME:
                await _resume_tasks(notifier_dict)
            if Config.INC_TASK_NOTIFY:
                await _notify_tasks(notifier_dict, chat_id, now)
            if not Config.INC_TASK_RESUME:
                await database.trunc_table("tasks")

    if await aiopath.isfile(".restartmsg"):
        try:
            await TgClient.bot.edit_message_text(
                chat_id=chat_id,
                message_id=msg_id,
                text=_restart_header(now, is_restart_chat=True),
                disable_web_page_preview=True,
            )
        except Exception as e:
            LOGGER.error(e)
        await remove(".restartmsg")


async def _notify_tasks(notifier_dict, restart_chat_id, now):
    for cid, data in notifier_dict.items():
        is_restart_chat = cid == restart_chat_id
        header = _restart_header(now, is_restart_chat)
        msg = header + "\n\n⌬ <b><i>Incomplete Tasks!</i></b>"
        for tag, tasks in data.items():
            entry = f"\n➲ <b>User:</b> {tag}\n┖ <b>Tasks:</b>"
            for index, task in enumerate(tasks, start=1):
                link = task.get("link", "")
                if link.startswith("http"):
                    entry += f" {index}. <a href='{link}'>L</a> |"
                else:
                    entry += f" {index}. L |"
            if len((msg + entry).encode()) > 4000:
                await _send_msg(cid, msg)
                msg = header
            msg += entry
        if msg:
            await _send_msg(cid, msg)


async def _resume_tasks(notifier_dict):
    for cid, data in notifier_dict.items():
        for tag, tasks in data.items():
            for task in tasks:
                command = task.get("command", "")
                user_id = task.get("user_id", 0)
                reply_to_msg_id = task.get("reply_to_msg_id", 0)
                thread_id = task.get("thread_id", 0)
                if not command or not user_id:
                    LOGGER.warning(
                        f"Resume: skipping task in {cid} "
                        f"(command={command!r}, user_id={user_id})"
                    )
                    continue
                try:
                    user = await TgClient.bot.get_users(user_id)
                except Exception as e:
                    LOGGER.warning(f"Resume: cannot get user {user_id}: {e}")
                    continue
                handler = resolve_command(command)
                if handler is None:
                    continue
                try:
                    LOGGER.info(f"Resume: starting {command!r} in {cid}")
                    msg = await TgClient.bot.send_message(
                        chat_id=cid,
                        text=command,
                        disable_notification=True,
                        message_thread_id=thread_id or None,
                    )
                    msg.text = command
                    msg.from_user = user
                    if reply_to_msg_id:
                        try:
                            reply_msg = await TgClient.bot.get_messages(
                                chat_id=cid, message_ids=reply_to_msg_id
                            )
                            if reply_msg:
                                msg.reply_to_message = reply_msg
                                msg.reply_to_message_id = reply_msg.id
                        except Exception as e:
                            LOGGER.warning(
                                f"Resume: cannot fetch reply msg {reply_to_msg_id}: {e}"
                            )
                    await handler(TgClient.bot, msg)
                    key = task.get("key")
                    if key:
                        await database.rm_incomplete_task(key)
                    else:
                        await database.rm_complete_task(task.get("link"))
                except Exception as e:
                    LOGGER.error(f"Resume: failed for '{command}' in {cid}: {e}")


@new_task
async def confirm_restart(_, query):
    await query.answer()
    data = query.data.split()
    message = query.message
    if data[1] == "confirm":
        reply_to = message.reply_to_message
        intervals["stopAll"] = True
        restart_message = await send_message(reply_to, "Restarting...")
        await delete_message(message)
        await TgClient.stop()
        if scheduler.running:
            scheduler.shutdown(wait=False)
        if qb := intervals["qb"]:
            qb.cancel()
        if st := intervals["status"]:
            for intvl in list(st.values()):
                intvl.cancel()
        await clean_all()
        await TorrentManager.close_all()
        proc1 = await create_subprocess_exec(
            "pkill",
            "-9",
            "-f",
            f"gunicorn|{BinConfig.ARIA2_NAME}|{BinConfig.QBIT_NAME}|{BinConfig.FFMPEG_NAME}|{BinConfig.FFPROBE_NAME}|{BinConfig.RCLONE_NAME}|{BinConfig.SEVENZ_NAME}|split",
        )
        proc2 = await create_subprocess_exec("python3", "update.py")
        await gather(proc1.wait(), proc2.wait())
        async with aiopen(".restartmsg", "w") as f:
            await f.write(f"{restart_message.chat.id}\n{restart_message.id}\n")
        osexecl(executable, executable, "-m", "bot")
    else:
        await delete_message(message)
