import asyncio
import threading


def run_async_in_thread(target_coroutine):
    def thread_target():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(target_coroutine)
        finally:
            loop.close()

    thread = threading.Thread(target=thread_target)
    thread.daemon = True
    thread.start()

    return thread
