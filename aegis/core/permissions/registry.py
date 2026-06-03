class CommandRegistry:
    # Music Module
    MUSIC_PLAY = "MUSIC_PLAY"
    MUSIC_PAUSE = "MUSIC_PAUSE"
    MUSIC_RESUME = "MUSIC_RESUME"
    MUSIC_SKIP = "MUSIC_SKIP"
    MUSIC_STOP = "MUSIC_STOP"
    MUSIC_QUEUE = "MUSIC_QUEUE"
    MUSIC_VOLUME = "MUSIC_VOLUME"
    MUSIC_NOWPLAYING = "MUSIC_NOWPLAYING"
    MUSIC_SHUFFLE = "MUSIC_SHUFFLE"
    MUSIC_CLEARQUEUE = "MUSIC_CLEARQUEUE"
    MUSIC_LYRICS = "MUSIC_LYRICS"

    # Giveaway Module
    GIVEAWAY_CREATE = "GIVEAWAY_CREATE"
    GIVEAWAY_REROLL = "GIVEAWAY_REROLL"
    GIVEAWAY_STOP = "GIVEAWAY_STOP"

    # Welcomer Module
    WELCOME_SET = "WELCOME_SET"

    # Tickets Module
    TICKET_PANEL = "TICKET_PANEL"
    TICKET_CLOSE = "TICKET_CLOSE"

    # Leveling Module
    LEVEL_RANK = "LEVEL_RANK"
    LEVEL_LEADERBOARD = "LEVEL_LEADERBOARD"
    LEVEL_SET_ROLE = "LEVEL_SET_ROLE"
    LEVEL_RESET = "LEVEL_RESET"

    # System/Admin Modules
    LINK_DASHBOARD = "LINK_DASHBOARD"
    UNLINK = "UNLINK"
    AUDIT_SERVER = "AUDIT_SERVER"
    OPTIMIZE_SERVER = "OPTIMIZE_SERVER"

    @classmethod
    def get_all_commands(cls) -> list[str]:
        return [
            v for k, v in cls.__dict__.items() 
            if not k.startswith("__") and isinstance(v, str)
        ]
