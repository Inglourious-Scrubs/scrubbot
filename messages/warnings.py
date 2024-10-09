# Warning messages

# First warning message
def first_warning(user, reason, channel_id_rules):
    message = (
        f"Dear {user},\n\n"
        f"This is a notification regarding a warning issues by the [DPS] staff:\n\n"
        f"Reason: *{reason}*\n\n"
        f"We'd like to remind you of the importance of following our server rules and honoring your commitments to schedules events. This helps maintain a positive environment for all members.\n\n"
        f"Please review the server rules in <#{channel_id_rules}> and ensure you can attend events you've signed up for. If you're unable to participate, kindly inform us in advance.\n\n"
        f"Thank you for your cooperation and understanding.\n\n"
        f"Best regards,\n"
        f"[DPS] Team"
    )
    return message

# Second warning message
def second_warning(user, reason, channel_id_rules):
    message = (
        f"Dear {user},\n\n"
        f"This is to inform you of a second warning issued by the [DPS] staff:\n\n"
        f"Reason: *{reason}*\n\n"
        f"We want to emphasize the importance of adhering to our server rules and respecting the time and effort put into organizing events. Your cooperation is crucial for a smooth and enjoyable experience for everyone involved.\n\n"
        f"Please take immediate action to address this issue. Review the server rules in <#{channel_id_rules}> and ensure you honour your commitments to events or provide timely notifications if you cannot attend.\n\n"
        f"We appreciate your prompt attention to this matter.\n\n"
        f"Best regards,\n"
        f"[DPS] Team"
    )
    return message

# Third warning message
def third_warning(user, reason, channel_id_rules):
    message = (
        f"Dear {user},\n\n"
        f"This is a final warning notification from the [DPS] staff:\n\n"
        f"Reason: *{reason}*\n\n"
        f"We must stress the extreme severity of this situation. Repeated violations of server rules or failure to honor event commitments have significantly impacted our community and the efforts of our event organizers.\n\n"
        f"This is your final opportunity to address these issues. Any further infractions will result in your immediate removal from both the guild and the Discord server. There will be no further warnings.\n\n"
        f"We strongly advise you to review and strictly adhere to the server rules in <#{channel_id_rules}>, and to fully commit to events you sign up for or provide ample notice if you cannot attend.\n\n"
        f"Your immediate and continued compliance is required to remain a member of our community.\n\n"
        f"Regards,\n"
        f"[DPS] Team"
    )
    return message

# Warning added, unable to DM user
def dm_user_error():
    return "Warning added, but unable to send a DM to the user."

# User received a warning
def user_received_warning(discord_id, warning_count):
    return f"User <@{discord_id}> has received a warning. Total warnings: {warning_count}"

# Notify mentor channel
def notify_mentor_channel():
    return "Couldn't send notification to Mentor's channel."

# No warnings to remove
def no_warnings():
    return "This user has no warnings to remove."

# Enter number of warning to remove
def warning_remove_number():
    return "Enter the number of the warning you want to remove:"

# Invalid warning number
def invalid_warning_number():
    return "Invalid warning number. Command cancelled."

# Warning removed
def warning_removed(warning_number):
    return f"Warning {warning_number} has been removed."

# Reason required for warning
def reason_required():
    return "A reason is required when adding a warning"
