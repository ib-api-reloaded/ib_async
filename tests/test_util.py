import asyncio
from threading import Thread

from ib_async import util


def test_get_current_loop():
    loop = util.getLoop()
    assert loop is not None


def test_create_new_loop():
    loop_holder = []

    def target():
        loop_holder.append(util.getLoop())

    thread1 = Thread(target=target)
    thread1.start()
    thread1.join()
    assert loop_holder[0] is not None

    thread2 = Thread(target=target)
    thread2.start()
    thread2.join()
    assert loop_holder[1] is not None
    assert loop_holder[0] is not loop_holder[1]


def test_loop_can_be_set():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    assert util.getLoop() is loop
