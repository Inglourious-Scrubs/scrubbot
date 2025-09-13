# Cross-check messages

# Inactivity message
def inactivity_message(discord_url):
    message = (
        f"Subject:\n"
        f"```\n"
        f"[DPS] - Inactivity/Missing link\n"
        f"```"
        f"Mail:\n"
        f"```\n"
        f"Hey!\n\n"
        f"We're cleaning up the roster and members inactive for 1 month+ or without a linked Discord ID will be removed. "
        f"Don't worry, we don't remove you from the [DPS] Discord server! If you return, just drop a message in the general channel for a re-invite.\n\n"
        f"If you're not on Discord anymore, here's the link to join again: {discord_url}\n\n"
        f"Hope to see you back soon!\n\n"
        f"```"
    )
    return message
