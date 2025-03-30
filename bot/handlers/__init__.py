from .accounts import router as accounts_router
from .source_chats import router as source_chats_router
from .target_chats import router as target_chats_router
from .parsing import router as parsing_router
from .invite_settings import router as invite_settings_router
from .inviting import router as inviting_router
from .main_menu import router as main_menu_router
from .lzt_autobuying import router as lzt_autobuying_router

routers = [
    main_menu_router,
    accounts_router,
    source_chats_router,
    target_chats_router,
    parsing_router,
    invite_settings_router,
    inviting_router,
    lzt_autobuying_router
] 