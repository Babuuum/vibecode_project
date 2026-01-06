from aiogram.fsm.state import State, StatesGroup


class SourceStates(StatesGroup):
    waiting_rss_url = State()
    waiting_page_url = State()
