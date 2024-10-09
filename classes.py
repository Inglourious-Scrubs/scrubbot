# Standard library imports
import os
import asyncio
import sqlite3
from datetime import datetime, timedelta, timezone

# Third-party imports
import discord
from discord import Interaction, app_commands, ui
from discord.ext import commands
from discord.ui import Button, View
import requests

# Personal files
from config import (DISCORD_INVITE_URL, ROLE_ID_CONFIRMATION, ROLE_ID_GUEST, ROLE_ID_MEMBER, ROLE_ID_STAFF,
                    ROLE_ID_BIRTHDAY, ROLE_ID_FAMED_MEMBER, GUILD_ID, API_KEY, CHANNEL_ID_MENTORS, CHANNEL_ID_RULES,
                    CURRENT_DB_FILENAME)
# Message imports
import messages.warnings as msg_warning
import messages.general as msg_general
import messages.mentor_application as msg_mentor_app
import messages.cross_check as msg_cross_check


# -------------- Classes for modals and buttons --------------
class GW2IDModal(ui.Modal, title='Verify your GW2 ID'):
    """Modal for GW2 ID verification."""
    gw2_id = ui.TextInput(label='Enter your GW2 ID (e.g., Example.1234)', style=discord.TextStyle.short)

    def __init__(self, cog):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await self.cog.process_verification(interaction, self.gw2_id.value)


class GW2IDUpdateModal(discord.ui.Modal, title='Update your GW2 ID'):
    def __init__(self, bot):
        super().__init__()
        self.bot = bot
        self.gw2_id = discord.ui.TextInput(label='Enter your GW2 ID (e.g., Example.1234)', style=discord.TextStyle.short)
        self.add_item(self.gw2_id)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await process_update(self.bot, interaction, self.gw2_id.value)


class AdminGW2IDUpdateModal(discord.ui.Modal, title="Update GW2 ID"):
    def __init__(self, interaction, user):
        super().__init__()
        self.interaction = interaction
        self.user = user
        self.gw2_id = discord.ui.TextInput(label="Main GW2 ID", required=False)
        self.alt_gw2_id = discord.ui.TextInput(label="Alt GW2 ID", required=False)
        self.add_item(self.gw2_id)
        self.add_item(self.alt_gw2_id)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await self.process_admin_update(interaction, self.user, self.gw2_id.value, self.alt_gw2_id.value)

    async def process_admin_update(self, interaction: discord.Interaction, target_user: discord.Member, new_gw2_id: str, new_alt_gw2_id: str):
        # Fetch the guild roster from the GW2 API
        response = requests.get(f"https://api.guildwars2.com/v2/guild/{GUILD_ID}/members", headers={"Authorization": f"Bearer {API_KEY}"})
        if response.status_code != 200:
            await interaction.followup.send("Failed to fetch guild roster. Please try again later.")
            return
        guild_roster = response.json()

        # Check if the provided GW2 IDs match any member in the guild roster
        main_member = next((m for m in guild_roster if m['name'].lower() == new_gw2_id.lower()), None) if new_gw2_id else None
        alt_member = next((m for m in guild_roster if m['name'].lower() == new_alt_gw2_id.lower()), None) if new_alt_gw2_id else None

        # Handle verification failures
        verification_failures = []
        if new_gw2_id and not main_member:
            verification_failures.append(f"{new_gw2_id} (main)")
        if new_alt_gw2_id and not alt_member:
            verification_failures.append(f"{new_alt_gw2_id} (alt)")

        if verification_failures:
            failure_msg = "Update failed. The following GW2 ID(s) were not found in the guild roster:\n\n"
            failure_msg += "\n".join(verification_failures)
            failure_msg += "\n\nPossible reasons:\n- Typo in the ID\n- User not in the guild\n- API key not updated (wait ~10 minutes and try again)"
            await interaction.followup.send(failure_msg, ephemeral=True)
            return

        conn = sqlite3.connect(CURRENT_DB_FILENAME)
        cursor = conn.cursor()

        try:
            # Fetch current user data
            cursor.execute("SELECT gw2_id, alt_gw2_id FROM users WHERE discord_id = ?", (str(target_user.id),))
            current_data = cursor.fetchone()
            current_main_id, current_alt_id = current_data if current_data else (None, None)

            swapped = False
            # Check if we're swapping main and alt
            if new_gw2_id and new_gw2_id == current_alt_id:
                new_gw2_id, new_alt_gw2_id = current_alt_id, current_main_id
                swapped = True
            elif new_alt_gw2_id and new_alt_gw2_id == current_main_id:
                new_gw2_id, new_alt_gw2_id = current_main_id, current_alt_id
                swapped = True
            elif new_gw2_id and new_gw2_id == current_main_id and new_alt_gw2_id and new_alt_gw2_id == current_alt_id:
                await interaction.followup.send("No changes were made as the provided IDs are the same as the current ones.", ephemeral=True)
                return
            elif new_gw2_id and not new_alt_gw2_id:
                new_alt_gw2_id = current_alt_id
            elif new_alt_gw2_id and not new_gw2_id:
                new_gw2_id = current_main_id

            if swapped:
                await interaction.followup.send(f"Swapped main and alt GW2 IDs for {target_user.mention}.", ephemeral=True)
            else:
                # Check for conflicts with existing accounts
                if new_gw2_id and new_gw2_id != current_main_id and new_gw2_id != current_alt_id:
                    cursor.execute("SELECT discord_id FROM users WHERE gw2_id = ? OR alt_gw2_id = ?", (new_gw2_id, new_gw2_id))
                    existing_main = cursor.fetchone()
                    if existing_main and str(existing_main[0]) != str(target_user.id):
                        await interaction.followup.send(f"The main GW2 ID ({new_gw2_id}) is already associated with another Discord account.", ephemeral=True)
                        return

                if new_alt_gw2_id and new_alt_gw2_id != current_main_id and new_alt_gw2_id != current_alt_id:
                    cursor.execute("SELECT discord_id FROM users WHERE gw2_id = ? OR alt_gw2_id = ?", (new_alt_gw2_id, new_alt_gw2_id))
                    existing_alt = cursor.fetchone()
                    if existing_alt and str(existing_alt[0]) != str(target_user.id):
                        await interaction.followup.send(f"The alternate GW2 ID ({new_alt_gw2_id}) is already associated with another Discord account.", ephemeral=True)
                        return

            # Prepare update data
            update_data = []
            update_fields = []
            if new_gw2_id:
                update_data.extend([new_gw2_id, "Member"])
                update_fields.extend(["gw2_id = ?", "guild_status = ?"])
            if new_alt_gw2_id:
                update_data.extend([new_alt_gw2_id, "Member"])
                update_fields.extend(["alt_gw2_id = ?", "alt_guild_status = ?"])

            if not update_data:
                await interaction.followup.send("No changes were made as no new valid IDs were provided.", ephemeral=True)
                return

            # Update the user's GW2 IDs in the database
            update_query = f"UPDATE users SET {', '.join(update_fields)} WHERE discord_id = ?"
            update_data.append(str(target_user.id))
            cursor.execute(update_query, tuple(update_data))
            conn.commit()

            # Prepare response message
            response_msg = f"Updated GW2 IDs for {target_user.mention}:\n"
            if new_gw2_id:
                response_msg += f"- {new_gw2_id} (main)\n"
            if new_alt_gw2_id:
                response_msg += f"- {new_alt_gw2_id} (alt)\n"

            # Notify mentors
            mentors_channel = interaction.client.get_channel(CHANNEL_ID_MENTORS)
            if mentors_channel:
                await mentors_channel.send(f"{interaction.user.mention} has updated GW2 IDs for {target_user.mention}.\n\n" + response_msg)

            await interaction.followup.send(response_msg, ephemeral=True)

        finally:
            conn.close()


class GuildInviteRequestModal(discord.ui.Modal):
    def __init__(self, invite_for: str, *args, **kwargs):
        super().__init__(title="Request Guild Invitation", *args, **kwargs)

        self.invite_for = invite_for

        # GW2 ID input field
        self.gw2_id = discord.ui.TextInput(
            label="Guild Wars 2 ID",
            placeholder="Enter your GW2 ID (e.g., Player.1234)",
            required=True,
            max_length=50
        )
        self.add_item(self.gw2_id)

    async def on_submit(self, interaction: discord.Interaction):
        gw2_id = self.gw2_id.value

        # Get the channel where mentors should be notified
        channel = interaction.guild.get_channel(CHANNEL_ID_MENTORS)

        # Prepare the message based on the selection
        if self.invite_for == "me":
            message = (
                f"🚨 __**Attention Needed**__ 🚨\n\n"
                f"{interaction.user.mention} is requesting an invite to the guild.\n\n"
                f"**GW2 ID**: ```{gw2_id}```")
        else:
            message = (
                f"🚨 __**Attention Needed**__ 🚨\n\n"
                f"{interaction.user.mention} is requesting an invite to the guild for a **friend**.\n\n"
                f"**GW2 ID**: ```{gw2_id}```")

        # Send the notification to the mentor channel
        if channel:
            await channel.send(message)
            await interaction.response.send_message(
                "Your request has been sent to the mentors. You or your friend will be invited to the guild soon!", ephemeral=True)
        else:
            await interaction.response.send_message(
                "Failed to send your request. Please contact a mentor directly.", ephemeral=True)


class ApplicationModalButton(discord.ui.Button):
    def __init__(self, bot: commands.Bot):
        super().__init__(style=discord.ButtonStyle.primary, label="Apply")
        self.bot = bot

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(ApplicationModalPart1(bot=self.bot))


class ApplicationModalPart1(discord.ui.Modal):
    def __init__(self, bot: commands.Bot):
        super().__init__(title="Staff Member Application - Part 1")
        self.bot = bot

    joined_how = discord.ui.TextInput(label="How did you join [DPS]?")
    timezone = discord.ui.TextInput(label="What's your UTC timezone?")
    has_commander_tag = discord.ui.TextInput(label="Do you own a commander/catmander tag?")

    async def on_submit(self, interaction: discord.Interaction):
        # Retrieve GW2 ID from the database
        conn = sqlite3.connect(CURRENT_DB_FILENAME)
        c = conn.cursor()
        c.execute("SELECT gw2_id FROM users WHERE discord_id = ?", (str(interaction.user.id),))
        result = c.fetchone()
        conn.close()

        if result is None or result[0] == 'Unknown':
            await interaction.response.send_message(
                "Error: Your GW2 ID is not found in our database. Please update your GW2 ID first.",
                ephemeral=True
            )
            return

        gw2_id = result[0]

        application_data = {
            "discord_id": str(interaction.user.id),
            "gw2_id": gw2_id,
            "joined_how": self.joined_how.value,
            "timezone": self.timezone.value,
            "has_commander_tag": self.has_commander_tag.value,
        }

        # Store this data temporarily
        if not hasattr(interaction.client, 'temp_application_data'):
            interaction.client.temp_application_data = {}

        interaction.client.temp_application_data[interaction.user.id] = application_data

        # Send a message with a button to continue
        await interaction.response.send_message(
            "Thank you for the initial information. Click the button below to continue your application.",
            view=ContinueApplicationView(bot=self.bot), ephemeral=True)


class ContinueApplicationView(discord.ui.View):
    def __init__(self, bot: commands.Bot):
        super().__init__()
        self.bot = bot

    @discord.ui.button(label="Continue Application", style=discord.ButtonStyle.primary)
    async def continue_application(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Pass the bot instance to the modal
        modal = ApplicationModalPart2(bot=self.bot)
        await interaction.response.send_modal(modal)


class ApplicationModalPart2(discord.ui.Modal):
    def __init__(self, bot: commands.Bot):
        super().__init__(title="Staff Member Application - Part 2")
        self.bot = bot

    content_preference = discord.ui.TextInput(label="What type of content do you enjoy?")
    has_led_event = discord.ui.TextInput(label="Have you ever led any event before?")
    event_interest = discord.ui.TextInput(label="Which events are you interested in leading?", required=False)
    changes_suggested = discord.ui.TextInput(label="Any changes you'd suggest for [DPS]?", required=False)

    async def on_submit(self, interaction: discord.Interaction):
        # Retrieve the data from part 1
        application_data = getattr(interaction.client, 'temp_application_data', {}).get(interaction.user.id, {})

        # Add the data from part 2
        application_data.update({
            "content_preference": self.content_preference.value,
            "has_led_event": self.has_led_event.value,
            "event_interest": self.event_interest.value,
            "changes_suggested": self.changes_suggested.value
        })

        # Save the complete application
        await self.save_application(interaction, application_data)

        # Inform Staff about the new application
        mentors_channel = self.bot.get_channel(CHANNEL_ID_MENTORS)
        if mentors_channel:
            try:
                await mentors_channel.send(
                    f"🚨 __**Attention needed**__ 🚨\n\n"
                    f"{interaction.user.mention} has submitted an application to become a Mentor"
                )
            except discord.DiscordException as e:
                print(f"Failed to send message to mentors channel: {e}")
        else:
            print(f"Mentors channel with ID {CHANNEL_ID_MENTORS} not found")

    @staticmethod
    async def save_application(interaction: discord.Interaction, application_data):
        try:
            conn = sqlite3.connect(CURRENT_DB_FILENAME)
            c = conn.cursor()
            c.execute('''
                INSERT INTO mentor_applications
                (discord_id, gw2_id, joined_how, timezone, has_commander_tag,
                content_preference, has_led_event, event_interest, changes_suggested)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                application_data["discord_id"],
                application_data["gw2_id"],
                application_data["joined_how"],
                application_data["timezone"],
                application_data["has_commander_tag"],
                application_data["content_preference"],
                application_data["has_led_event"],
                application_data["event_interest"],
                application_data["changes_suggested"]
            ))
            conn.commit()
            conn.close()
            await interaction.response.send_message("Your application has been submitted successfully!", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"An error occurred while submitting your application: {str(e)}",
                                                    ephemeral=True)


class WelcomeButton(ui.Button):
    """Button for sending welcome messages."""

    def __init__(self, user: discord.Member):
        super().__init__(style=discord.ButtonStyle.primary, label="Send welcome message")
        self.user = user

    async def callback(self, interaction: Interaction):
        await interaction.response.send_message(
            f"To welcome the new member copy and run the following command: ```!welcome {self.user.mention}```",
            ephemeral=True)
        self.disabled = True
        self.label = "Welcome message sent"
        await interaction.message.edit(view=self.view)


class InvitationButton(ui.Button):
    """Button for confirming that the in-game guild invitation has been sent."""

    def __init__(self, new_gw2_id: str):
        super().__init__(style=discord.ButtonStyle.primary, label="Send guild invitation")
        self.gw2_id = new_gw2_id

    async def callback(self, interaction: Interaction):
        await interaction.response.send_message(f"Please send a guild invite to: ```{self.gw2_id}```", ephemeral=True)
        self.disabled = True
        self.label = "Guild invitation sent"
        await interaction.message.edit(view=self.view)


class AddToWatchlistModal(ui.Modal, title='Add Player to Watchlist'):
    reason = ui.TextInput(label='Reason', style=discord.TextStyle.paragraph)

    def __init__(self, cog, discord_id, identifier):
        super().__init__()
        self.cog = cog
        self.discord_id = discord_id
        self.identifier = identifier

    async def on_submit(self, interaction: discord.Interaction):
        conn = None
        try:
            conn = sqlite3.connect(CURRENT_DB_FILENAME)
            c = conn.cursor()

            c.execute('''
                UPDATE users
                SET watchlist_reason = ?
                WHERE discord_id = ?
            ''', (self.reason.value, self.discord_id))

            conn.commit()

            await interaction.response.send_message(
                f"User with identifier '{self.identifier}' has been added to the watchlist. Reason: {self.reason.value}",
                ephemeral=True)

        except sqlite3.Error as e:
            await interaction.response.send_message(f"An error occurred while updating the database: {e}",
                                                    ephemeral=True)
        finally:
            if conn:
                conn.close()


class WarningsButton(ui.Button):
    """Button for viewing user warnings."""

    def __init__(self, cog, user_id, warnings):
        super().__init__(style=discord.ButtonStyle.primary, label="View Warnings")
        self.cog = cog
        self.user_id = user_id
        self.warnings = warnings

    async def callback(self, interaction: discord.Interaction):
        try:
            await display_warnings(interaction, self.user_id, self.warnings)
        except Exception as e:
            print(f"Error in WarningsButton callback: {e}")
            await interaction.response.send_message(
                "An error occurred while displaying warnings. Please try again later.", ephemeral=True)


class ApplicationView(View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label="See details", style=discord.ButtonStyle.primary)
    async def see_details(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Enter the ID of the application you want to view:", ephemeral=True)

        def check(m):
            return m.author == interaction.user and m.channel == interaction.channel and m.content.isdigit()

        try:
            msg = await self.bot.wait_for('message', check=check, timeout=60.0)
        except asyncio.TimeoutError:
            await interaction.followup.send(msg_general.no_response(), ephemeral=True)
            return

        app_id = int(msg.content)
        await msg.delete()  # Delete the user's input message

        # Fetch the full application details
        conn = sqlite3.connect(CURRENT_DB_FILENAME)
        c = conn.cursor()
        c.execute("SELECT * FROM mentor_applications WHERE id = ?", (app_id,))
        app_details = c.fetchone()
        conn.close()

        if not app_details:
            await interaction.followup.send("Invalid application ID.", ephemeral=True)
            return

        # Create a detailed embed for the selected application
        detail_embed = discord.Embed(title=f"Application ID {app_details[0]} - Details",
                                     color=discord.Color.green())

        # Set the author of the embed
        author_id = app_details[2]
        author = await self.bot.fetch_user(author_id)
        detail_embed.set_author(name=f"{author.display_name}", icon_url=author.display_avatar.url)

        detail_embed.add_field(name="\u200b", value="", inline=False)
        detail_embed.add_field(name="Timestamp", value=app_details[1], inline=False)
        detail_embed.add_field(name="\u200b", value="", inline=False)
        detail_embed.add_field(name="Discord", value=f"<@{author_id}>", inline=True)
        detail_embed.add_field(name="GW2 ID", value=app_details[3], inline=True)
        detail_embed.add_field(name="\u200b", value="", inline=False)
        detail_embed.add_field(name="How did you join [DPS]?", value=app_details[4], inline=False)
        detail_embed.add_field(name="What's your UTC Timezone?", value=app_details[5], inline=False)
        detail_embed.add_field(name="Do you own a Commander Tag?", value=app_details[6], inline=False)
        detail_embed.add_field(name="What type of content do you enjoy?", value=app_details[7], inline=False)
        detail_embed.add_field(name="Have you ever led any event before?", value=app_details[8], inline=False)
        detail_embed.add_field(name="Which events are you interested in leading?", value=app_details[9] or "N/A",
                               inline=False)
        detail_embed.add_field(name="Any changes you'd suggest for [DPS]?", value=app_details[10] or "N/A",
                               inline=False)

        # Set thumbnail
        script_dir = os.path.dirname(os.path.abspath(__file__))
        thumbnail_path = os.path.join(script_dir, "pictures", "Application_details.png")

        if os.path.exists(thumbnail_path):
            file = discord.File(thumbnail_path, filename="Application_details.png")
            detail_embed.set_thumbnail(url="attachment://Application_details.png")
        else:
            file = None
            print(f"Thumbnail file not found at: {thumbnail_path}")

        await interaction.followup.send(file=file, embed=detail_embed, ephemeral=True)

    @discord.ui.button(label="Remove application", style=discord.ButtonStyle.danger)
    async def remove_application(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Enter the ID of the application you want to remove:", ephemeral=True)

        def check(m):
            return m.author == interaction.user and m.channel == interaction.channel and m.content.isdigit()

        try:
            msg = await self.bot.wait_for('message', check=check, timeout=30.0)
        except asyncio.TimeoutError:
            await interaction.followup.send(msg_general.no_response(), ephemeral=True)
            return

        app_id = int(msg.content)
        await msg.delete()  # Delete the user's input message

        # Remove the application from the database
        conn = sqlite3.connect(CURRENT_DB_FILENAME)
        c = conn.cursor()
        c.execute("DELETE FROM mentor_applications WHERE id = ?", (app_id,))
        conn.commit()
        conn.close()

        if c.rowcount == 0:
            await interaction.followup.send("Invalid application ID.", ephemeral=True)
        else:
            await interaction.followup.send(f"Application ID {app_id} has been removed.", ephemeral=True)


class Paginator(discord.ui.View):
    """A general-purpose paginator for displaying embeds."""

    def __init__(self, embeds):
        super().__init__(timeout=180)
        self.embeds = embeds
        self.current_page = 0

    @discord.ui.button(label="◀️", style=discord.ButtonStyle.grey)
    async def previous_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = (self.current_page - 1) % len(self.embeds)
        await interaction.response.edit_message(embed=self.embeds[self.current_page], view=self)

    @discord.ui.button(label="▶️", style=discord.ButtonStyle.grey)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = (self.current_page + 1) % len(self.embeds)
        await interaction.response.edit_message(embed=self.embeds[self.current_page], view=self)


class BirthdayModal(ui.Modal, title="Set Your Birthday"):
    def __init__(self, cog):
        super().__init__()
        self.cog = cog

        # Day input field
        self.day_input = ui.TextInput(
            label="Enter your birthday day (1-31)",
            placeholder="e.g., 15",
            required=True,
            min_length=1,
            max_length=2,
            style=discord.TextStyle.short
        )

        # Month input field
        self.month_input = ui.TextInput(
            label="Enter your birthday month (1-12)",
            placeholder="e.g., 7 for July",
            required=True,
            min_length=1,
            max_length=2,
            style=discord.TextStyle.short
        )

        # Year input field
        self.year_input = ui.TextInput(
            label="Enter your birthday year",
            placeholder="e.g., 1990",
            required=True,
            min_length=4,
            max_length=4,
            style=discord.TextStyle.short
        )

        # Add items to the modal
        self.add_item(self.day_input)
        self.add_item(self.month_input)
        self.add_item(self.year_input)

    async def on_submit(self, interaction: discord.Interaction):
        day = self.day_input.value
        month = self.month_input.value
        year = self.year_input.value

        # Validate day, month, and year inputs
        if not (day.isdigit() and month.isdigit() and year.isdigit()):
            await interaction.response.send_message("Please enter valid numbers for day, month, and year.",
                                                    ephemeral=True)
            return

        day = int(day)
        month = int(month)
        year = int(year)

        if day < 1 or day > 31:
            await interaction.response.send_message("Day must be between 1 and 31.", ephemeral=True)
            return

        if month < 1 or month > 12:
            await interaction.response.send_message("Month must be between 1 and 12.", ephemeral=True)
            return

        if year < 1900 or year > datetime.now().year:
            await interaction.response.send_message("Year must be between 1900 and the current year.", ephemeral=True)
            return

        # Save to database
        conn = sqlite3.connect(CURRENT_DB_FILENAME)
        c = conn.cursor()
        c.execute("UPDATE users SET birthday = ? WHERE discord_id = ?",
                  (f"{day:02d}.{month:02d}.{year}", str(interaction.user.id)))
        conn.commit()
        conn.close()

        await interaction.response.send_message(f"Your birthday has been set to {day:02d}.{month:02d}.{year}!",
                                                ephemeral=True)


# -------------- Functions ----------------
async def display_warnings(interaction: discord.Interaction, user_id: str, warnings):
    """Display warnings for a user."""
    user = await interaction.client.fetch_user(int(user_id))
    embed = discord.Embed(title="__**Warnings**__", color=discord.Color.yellow())

    # Set author (this will display the avatar, nickname, and mention)
    embed.set_author(name=f"{user.display_name}", icon_url=user.display_avatar.url)
    embed.description = f"{user.mention}"

    def format_date(date_string):
        try:
            date_obj = datetime.fromisoformat(date_string)
            return date_obj.strftime("%B %d %Y at %I:%M %p")  # e.g., "July 14 2024 at 11:47 PM"
        except ValueError:
            return "Unknown Date"

    script_dir = os.path.dirname(os.path.abspath(__file__))
    thumbnail_path = os.path.join(script_dir, "pictures", "Warnings.png")

    if os.path.exists(thumbnail_path):
        file = discord.File(thumbnail_path, filename="Warnings.png")
        embed.set_thumbnail(url="attachment://Warnings.png")
    else:
        file = None
        print(f"Thumbnail file not found at: {thumbnail_path}")

    def get_ordinal_suffix(n):
        if 11 <= n % 100 <= 13:
            return 'th'
        else:
            return {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')

    for i, warning in enumerate(sorted(warnings, key=lambda x: x[3]), 1):
        embed.add_field(
            name=f"{i}{get_ordinal_suffix(i)} Warning",
            value=f"__Reason:__ {warning[2]}\n__Date:__ {format_date(warning[3])}",
            inline=False
        )

    try:
        if interaction.response.is_done():
            await interaction.followup.send(file=file, embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(file=file, embed=embed, ephemeral=True)
    except discord.errors.NotFound:
        # If the interaction has expired, send a new message in the channel
        await interaction.channel.send(f"{interaction.user.mention}, here are the warnings:", file=file,
                                       embed=embed)
    except Exception as e:
        print(f"Error displaying warnings: {e}")


async def process_update(bot, interaction: discord.Interaction, new_gw2_id: str):
    # Fetch the guild roster from the GW2 API
    response = requests.get(f"https://api.guildwars2.com/v2/guild/{GUILD_ID}/members",
                            headers={"Authorization": f"Bearer {API_KEY}"})
    if response.status_code != 200:
        await interaction.followup.send("Failed to fetch guild roster. Please try again later.")
        return
    guild_roster = response.json()

    # Check if the provided GW2 ID matches any member in the guild roster
    matching_member = next((m for m in guild_roster if m['name'].lower() == new_gw2_id.lower()), None)

    if matching_member:
        # Connect to the database
        conn = sqlite3.connect(CURRENT_DB_FILENAME)
        cursor = conn.cursor()

        try:
            # Fetch current user data
            cursor.execute("SELECT gw2_id, alt_gw2_id FROM users WHERE discord_id = ?", (str(interaction.user.id),))
            current_data = cursor.fetchone()
            current_main_id, current_alt_id = current_data if current_data else (None, None)

            swapped = False
            # Check if we're swapping main and alt
            if new_gw2_id == current_alt_id:
                new_main_id, new_alt_id = current_alt_id, current_main_id
                swapped = True
            else:
                new_main_id, new_alt_id = new_gw2_id, current_alt_id

            # Check for conflicts with existing accounts
            cursor.execute("SELECT discord_id FROM users WHERE gw2_id = ? OR alt_gw2_id = ?",
                           (new_main_id, new_main_id))
            existing_user = cursor.fetchone()
            if existing_user and str(existing_user[0]) != str(interaction.user.id):
                await interaction.followup.send(
                    f"This Guild Wars 2 ID ({new_main_id}) is already associated with another Discord account. Contact staff if you believe this is an error.",
                    ephemeral=True)
                mentors_channel = self.bot.get_channel(CHANNEL_ID_MENTORS)
                if mentors_channel:
                    await mentors_channel.send(
                        f"🚨 __**Suspicious Activity**__ 🚨\n\n"
                        f"User {interaction.user.mention} attempted to verify with GW2 ID:\n\n"
                        f"*{new_main_id}*\n\n"
                        f"This ID is already associated with <@{existing_user[0]}>.")
                return

            # Update the user's GW2 ID in the database
            cursor.execute("UPDATE users SET gw2_id = ?, alt_gw2_id = ?, guild_status = ? WHERE discord_id = ?",
                           (new_main_id, new_alt_id, "Member", str(interaction.user.id)))
            conn.commit()

            if swapped:
                await interaction.followup.send(
                    f"Your main and alt Guild Wars 2 IDs have been swapped. Main ID is now {new_main_id}.",
                    ephemeral=True)
            else:
                await interaction.followup.send(f"Your Guild Wars 2 ID has been updated to {new_main_id}.",
                                                ephemeral=True)

            # Notify mentors
            mentors_channel = bot.get_channel(CHANNEL_ID_MENTORS)
            if mentors_channel:
                if swapped:
                    await mentors_channel.send(
                        f"{interaction.user.mention} has swapped their main and alt GW2 IDs. Main ID is now {new_main_id}.")
                else:
                    await mentors_channel.send(
                        f"{interaction.user.mention} has updated their GW2 ID to {new_main_id}.")

        finally:
            conn.close()
    else:
        # Explain possible reasons for not finding a match
        await interaction.followup.send(
            f"The GW2 ID {new_gw2_id} was not found in the guild roster. This might be because:\n"
            f"- There is a typo in the ID provided\n"
            f"- You are not currently a member of the guild\n"
            f"- The API key has not updated yet. Please wait about 10 minutes and try verifying again.",
            ephemeral=True)

        # Ask if the user needs an invitation
        view = discord.ui.View()
        view.add_item(discord.ui.Button(label="Yes", style=discord.ButtonStyle.green, custom_id="yes"))
        view.add_item(discord.ui.Button(label="No", style=discord.ButtonStyle.red, custom_id="no"))

        await interaction.followup.send("Do you need an invitation to the guild?", view=view, ephemeral=True)

        try:
            interaction_response = await self.bot.wait_for(
                "interaction",
                check=lambda i: i.user.id == interaction.user.id and i.data["custom_id"] in ["yes", "no"],
                timeout=180.0
            )

            if interaction_response.data["custom_id"] == "yes":
                await interaction_response.response.send_message(
                    "[DPS] staff has been notified to invite you back to the guild.\n\n"
                    "Please run this command again once you've joined the guild.", ephemeral=True)

                # Notify mentors
                mentors_channel = self.bot.get_channel(CHANNEL_ID_MENTORS)
                if mentors_channel:
                    view = discord.ui.View().add_item(InvitationButton(new_gw2_id))
                    await mentors_channel.send(
                        f"🚨 __**Attention Needed**__ 🚨\n\n"
                        f"{interaction.user.mention} needs to be invited to the guild with GW2 ID: {new_gw2_id}\n"
                        f"Please invite them back to the guild.", view=view)
            else:
                await interaction_response.response.send_message(
                    "Alright, the process has been interrupted. No changes have been made to your GW2 ID.",
                    ephemeral=True)

        except asyncio.TimeoutError:
            await interaction.followup.send("You didn't respond in time. No changes have been made to your GW2 ID.",
                                            ephemeral=True)


# -------------- Cogs ----------------
class ConfirmationCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="verify", description="Verify your GW2 ID with the guild roster")
    @app_commands.checks.has_role(ROLE_ID_CONFIRMATION)
    async def verify(self, interaction: discord.Interaction):

        # Display the modal to collect the GW2 ID
        await interaction.response.send_modal(GW2IDModal(self))

    async def process_verification(self, interaction: discord.Interaction, gw2_id: str,
                                   target_user: discord.Member = None):
        # Fetch the guild roster from the GW2 API
        response = requests.get(f"https://api.guildwars2.com/v2/guild/{GUILD_ID}/members",
                                headers={"Authorization": f"Bearer {API_KEY}"})
        if response.status_code != 200:
            await interaction.followup.send("Failed to fetch guild roster. Please try again later.", ephemeral=True)
            return
        guild_roster = response.json()

        # Check if the provided GW2 ID matches any member in the guild roster
        matching_member = next((m for m in guild_roster if m['name'].lower() == gw2_id.lower()), None)

        # Use target_user if provided, otherwise use interaction.user
        user_to_verify = target_user or interaction.user

        if matching_member:
            # Connect to the database (using sqlite3, which is synchronous)
            conn = sqlite3.connect(CURRENT_DB_FILENAME)
            cursor = conn.cursor()

            # Check if the GW2 ID is already associated with another Discord account
            cursor.execute("SELECT discord_id FROM users WHERE gw2_id = ?", (gw2_id,))
            existing_user = cursor.fetchone()
            if existing_user:
                await interaction.followup.send(
                    f"This Guild Wars 2 ID ({gw2_id}) is already associated with another Discord account. Contact staff if you believe this is an error.",
                    ephemeral=True)
                mentors_channel = self.bot.get_channel(CHANNEL_ID_MENTORS)
                if mentors_channel:
                    await mentors_channel.send(
                        f"🚨 __**Suspicious Activity**__ 🚨\n\n"
                        f"User {user_to_verify.mention} attempted to verify with GW2 ID:\n\n"
                        f"*{gw2_id}*\n\n"
                        f"This ID is already associated with <@{existing_user[0]}>.")
                conn.close()
                return

            # If a match is found, add the GW2 ID to the database and assign the member role
            cursor.execute("INSERT OR REPLACE INTO users (discord_id, gw2_id, guild_status) VALUES (?, ?, ?)",
                           (str(user_to_verify.id), matching_member['name'], 'Member'))
            conn.commit()
            conn.close()

            # Remove all roles from the user except the default role
            roles_to_remove = [role for role in user_to_verify.roles if role != interaction.guild.default_role]
            await user_to_verify.remove_roles(*roles_to_remove)

            # Add the member role
            member_role = discord.utils.get(interaction.guild.roles, id=ROLE_ID_MEMBER)
            if member_role:
                await user_to_verify.add_roles(member_role)

            await interaction.followup.send(
                f"__**Verification successful!**__\n\n"
                f"The GW2 ID ({matching_member['name']}) has been added to our database and {user_to_verify.mention} has been assigned the member role.",
                ephemeral=True)

            mentors_channel = self.bot.get_channel(CHANNEL_ID_MENTORS)
            if mentors_channel:
                view = discord.ui.View().add_item(WelcomeButton(user_to_verify))
                await mentors_channel.send(
                    f"{user_to_verify.mention} has been verified with GW2 ID: {matching_member['name']}", view=view)
        else:
            # If no match is found, notify the user
            await interaction.followup.send(
                f"__**Verification failed**__\n"
                f"The GW2 ID\n\n"
                f"*{gw2_id}*\n\n"
                f"was not found in the guild roster. This might be because:\n"
                f"- there is a typo in the ID provided\n"
                f"- the user is not currently a member of the guild\n"
                f"- the API key has not updated yet. Please wait about 10 minutes and try verifying again.",
                ephemeral=True)

    @verify.error
    async def verify_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.errors.MissingRole):
            await interaction.response.send_message(
                msg_general.invalid_permission(),
                ephemeral=True)
        else:
            await interaction.response.send_message(f"An error occurred: {str(error)}", ephemeral=True)

    @app_commands.command(name="guest", description="Assign the guest role to a user")
    @app_commands.checks.has_role(ROLE_ID_CONFIRMATION)
    async def guest(self, interaction: discord.Interaction):
        """Command to assign the guest role to a user."""
        await interaction.response.defer(ephemeral=True)

        guest_role = discord.utils.get(interaction.guild.roles, id=ROLE_ID_GUEST)
        if not guest_role:
            await interaction.followup.send("Error: Guest role not found.", ephemeral=True)
            return

        try:
            await interaction.user.add_roles(guest_role)
            await interaction.followup.send(
                "The guest role has been assigned to you successfully. You now have access to the voice channels",
                ephemeral=True
            )
        except discord.Forbidden:
            await interaction.followup.send("I do not have permission to assign roles.", ephemeral=True)
        except discord.HTTPException:
            await interaction.followup.send(
                "An error occurred while assigning the role. Please try again later.",
                ephemeral=True
            )

    @guest.error
    async def guest_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.errors.MissingRole):
            await interaction.response.send_message(
                msg_general.invalid_permission(),
                ephemeral=True)
        else:
            await interaction.response.send_message(f"An error occurred: {str(error)}", ephemeral=True)

    @app_commands.command(name="guild-invite", description="Request an invitation to the guild")
    @app_commands.checks.has_any_role(ROLE_ID_MEMBER, ROLE_ID_CONFIRMATION)
    async def guild_invite(self, interaction: discord.Interaction):
        # Check if the user has the member role
        for_member = discord.utils.get(interaction.user.roles, id=ROLE_ID_MEMBER) is not None

        # If user is a member, ask if the invite is for them or a friend
        if for_member:
            # Create the view with two buttons for "Me" and "Friend"
            view = View()
            view.add_item(Button(label="Me", style=discord.ButtonStyle.primary, custom_id="invite_me"))
            view.add_item(Button(label="Friend", style=discord.ButtonStyle.primary, custom_id="invite_friend"))

            # Send the response with the buttons
            await interaction.response.send_message("Is this invite for you or a friend?", view=view, ephemeral=True)

            # Handle button interaction
            def check(button_interaction: discord.Interaction):
                return button_interaction.data["custom_id"] in ["invite_me", "invite_friend"]

            button_interaction = await interaction.client.wait_for("interaction", check=check)

            if button_interaction.data["custom_id"] == "invite_me":
                await button_interaction.response.send_modal(GuildInviteRequestModal("me"))
            else:
                await button_interaction.response.send_modal(GuildInviteRequestModal("friend"))

        else:
            # If the user is in the confirmation role, directly ask for the GW2 ID
            await interaction.response.send_modal(GuildInviteRequestModal("me"))

    @guild_invite.error
    async def guild_invite_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.errors.MissingAnyRole):
            await interaction.response.send_message(
                msg_general.invalid_permission(),
                ephemeral=True
            )
        else:
            await interaction.response.send_message(f"An error occurred: {str(error)}", ephemeral=True)


class MemberCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="birthday", description="Set or remove your birthday")
    @app_commands.checks.has_role(ROLE_ID_MEMBER)
    @app_commands.choices(action=[app_commands.Choice(name="Set your birthday", value="set"),
                                  app_commands.Choice(name="Remove your birthday", value="remove")])
    async def birthday(self, interaction: discord.Interaction, action: str):

        if action == "set":
            await interaction.response.send_modal(BirthdayModal(self))
        elif action == "remove":
            conn = sqlite3.connect(CURRENT_DB_FILENAME)
            c = conn.cursor()

            try:
                c.execute("UPDATE users SET birthday = '-' WHERE discord_id = ?", (str(interaction.user.id),))
                conn.commit()

                # Remove birthday role if present
                birthday_role = interaction.guild.get_role(ROLE_ID_BIRTHDAY)
                if birthday_role and birthday_role in interaction.user.roles:
                    await interaction.user.remove_roles(birthday_role)

                await interaction.response.send_message("Your birthday has been removed.", ephemeral=True)
            except sqlite3.Error as e:
                await interaction.response.send_message(f"An error occurred while removing your birthday: {e}",
                                                        ephemeral=True)
            finally:
                conn.close()

    @birthday.error
    async def birthday_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.errors.MissingRole):
            await interaction.response.send_message("You must be a member to use this command.", ephemeral=True)
        else:
            await interaction.response.send_message(f"An error occurred: {str(error)}", ephemeral=True)

    @app_commands.command(name="apply-mentor", description="Apply for a staff position in [DPS]")
    @app_commands.checks.has_role(ROLE_ID_MEMBER)
    async def apply_mentor(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title=msg_mentor_app.apply_title(),
            description=msg_mentor_app.apply_description(),
            color=discord.Color.blue()
        )

        view = discord.ui.View()
        view.add_item(ApplicationModalButton(bot=self.bot))

        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @apply_mentor.error
    async def apply_mentor_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.errors.MissingRole):
            await interaction.response.send_message("You must be a member to apply for a staff position.",
                                                    ephemeral=True)
        else:
            await interaction.response.send_message(f"An error occurred: {str(error)}", ephemeral=True)

    @app_commands.command(name="whois", description="Get user information")
    @app_commands.describe(identifier="The user's @mention, Discord ID, or GW2 ID")
    @app_commands.checks.has_role(ROLE_ID_MEMBER)
    async def whois(self, interaction: discord.Interaction, identifier: str):
        await interaction.response.defer(ephemeral=True)

        conn = None
        try:
            conn = sqlite3.connect(CURRENT_DB_FILENAME)
            c = conn.cursor()

            # Find user in database
            discord_id = identifier[2:-1] if identifier.startswith('<@') and identifier.endswith('>') else identifier
            discord_id = discord_id[1:] if discord_id.startswith('!') else discord_id

            for query in [
                "SELECT * FROM users WHERE discord_id = ?",
                "SELECT * FROM users WHERE gw2_id = ?",
                "SELECT * FROM users WHERE alt_gw2_id = ?"
            ]:
                c.execute(query, (discord_id,))
                user_data = c.fetchone()
                if user_data:
                    break

            if not user_data:
                await interaction.followup.send("User not found in the database.", ephemeral=True)
                return

            column_names = [description[0] for description in c.description]
            discord_user = await self.bot.fetch_user(int(user_data[column_names.index('discord_id')]))
            discord_member = interaction.guild.get_member(discord_user.id)

            embed = discord.Embed(color=discord_member.color if discord_member else discord.Color.blue())
            embed.set_author(name=f"{discord_member.display_name if discord_member else discord_user.name}",
                             icon_url=discord_user.display_avatar.url)
            embed.set_thumbnail(url=discord_user.display_avatar.url)
            embed.description = f"{discord_user.mention}"

            # Common fields
            gw2_id, guild_status = user_data[column_names.index('gw2_id')], user_data[
                column_names.index('guild_status')]
            alt_gw2_id, alt_guild_status = user_data[column_names.index('alt_gw2_id')], user_data[
                column_names.index('alt_guild_status')]

            if any(role.id in [ROLE_ID_STAFF, ROLE_ID_FAMED_MEMBER] for role in interaction.user.roles):
                embed.add_field(name="🆔 Guild Wars 2", value=f"{gw2_id}\n{alt_gw2_id}", inline=True)
                embed.add_field(name="🎖️ Guild Status", value=f"{guild_status}\n{alt_guild_status}", inline=True)
            else:
                embed.add_field(name="🆔 Guild Wars 2", value=gw2_id, inline=True)
                embed.add_field(name="🎖️ Guild Status", value=guild_status, inline=True)
            embed.add_field(name="\u200b", value="", inline=False)

            # Fetch guild roster and get join date
            response = requests.get(f"https://api.guildwars2.com/v2/guild/{GUILD_ID}/members",
                                    headers={"Authorization": f"Bearer {API_KEY}"})
            if response.status_code != 200:
                await interaction.followup.send("Failed to fetch the guild roster. Please try again later.",
                                                ephemeral=True)
                return

            guild_roster = response.json()
            gw2_join_date = next(
                (member.get('joined') for member in guild_roster if member["name"].lower() == gw2_id.lower()), None)
            joined_gw2_date = datetime.strptime(gw2_join_date, "%Y-%m-%dT%H:%M:%S.%fZ").strftime(
                "%b %d, %Y") if gw2_join_date else "-"

            embed.add_field(name="📅 Guild joined", value=joined_gw2_date, inline=True)
            embed.add_field(name="🎂 Birthday", value=user_data[column_names.index('birthday')], inline=True)
            embed.add_field(name="\u200b", value="", inline=False)

            if discord_member:
                roles = [role.mention for role in discord_member.roles if role.name != "@everyone"]
                embed.add_field(name=f"⚙️ Roles [{len(roles)}]", value=" ".join(roles) if roles else "No roles",
                                inline=False)

            # Additional information for staff and famed members
            if any(role.id in [ROLE_ID_STAFF, ROLE_ID_FAMED_MEMBER] for role in interaction.user.roles):
                if discord_member:
                    permissions = []
                    if discord_member.guild_permissions.administrator:
                        permissions.append("Administrator")
                    else:
                        for perm in ['manage_guild', 'ban_members', 'kick_members']:
                            if getattr(discord_member.guild_permissions, perm):
                                permissions.append(perm.replace('_', ' ').title())
                    embed.add_field(name="\u200b", value="", inline=False)
                    embed.add_field(name="🔑 Key Permissions",
                                    value=", ".join(permissions) if permissions else "No key permissions", inline=True)

                acknowledgements = []
                if interaction.guild.owner_id == discord_user.id:
                    acknowledgements.append("Server Owner")
                elif discord_member and discord_member.guild_permissions.administrator:
                    acknowledgements.append("Server Admin")
                if acknowledgements:
                    embed.add_field(name="🏆 Acknowledgements", value=", ".join(acknowledgements), inline=True)

                watchlist_status = "Yes" if user_data[5] != '-' else "No"
                embed.add_field(name="\u200b", value="", inline=False)
                embed.add_field(name="🚨 On watchlist", value=watchlist_status, inline=True)

                c.execute("SELECT * FROM warnings WHERE discord_id = ?", (user_data[0],))
                warnings = c.fetchall()
                embed.add_field(name="⚠️ Warnings", value=str(len(warnings)), inline=True)

                embed.set_footer(text=f"ID: {discord_user.id} • {datetime.now().strftime('%m/%d/%Y %I:%M %p')}")

                if watchlist_status == "Yes":
                    embed.add_field(name="\u200b", value="", inline=False)
                    embed.add_field(name="Watchlist Reason", value=f"{user_data[5]}", inline=False)

                view = discord.ui.View()
                if warnings:
                    view.add_item(WarningsButton(self, user_data[0], warnings))
                await interaction.followup.send(embed=embed, view=view)
            else:
                await interaction.followup.send(embed=embed)

        except sqlite3.Error as e:
            await interaction.followup.send(f"A database error occurred: {e}", ephemeral=True)
        except discord.HTTPException as e:
            await interaction.followup.send(f"An error occurred while sending the message: {e}", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"An unexpected error occurred: {e}", ephemeral=True)
        finally:
            if conn:
                conn.close()

    @whois.error
    async def whois_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.errors.MissingRole):
            await interaction.response.send_message(
                msg_general.invalid_permission(), ephemeral=True)
        else:
            await interaction.response.send_message(f"An error occurred: {str(error)}", ephemeral=True)

    @app_commands.command(name="gw2id", description="Update or remove your Guild Wars 2 ID")
    @app_commands.checks.has_role(ROLE_ID_MEMBER)
    @app_commands.choices(action=[
        app_commands.Choice(name="Update", value="update"),
        app_commands.Choice(name="Remove", value="remove")
    ])
    async def gw2id(self, interaction: discord.Interaction, action: app_commands.Choice[str]):
        if action.value == "update":
            await interaction.response.send_modal(GW2IDUpdateModal(self.bot))
        elif action.value == "remove":
            conn = sqlite3.connect(CURRENT_DB_FILENAME)
            c = conn.cursor()
            try:
                c.execute("UPDATE users SET gw2_id = '-', guild_status = '-' WHERE discord_id = ?", (str(interaction.user.id),))
                conn.commit()
                await interaction.response.send_message("Your Guild Wars 2 ID has been removed.", ephemeral=True)
            except sqlite3.Error as e:
                await interaction.response.send_message(f"An error occurred: {e}", ephemeral=True)
            finally:
                conn.close()

    @gw2id.error
    async def gw2id_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.errors.MissingRole):
            await interaction.response.send_message("You must be a member to update your GW2 ID.", ephemeral=True)
        else:
            await interaction.response.send_message(f"An error occurred: {str(error)}", ephemeral=True)


class StaffCog(commands.Cog):
    """Cog for staff-related commands and functions."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="admin-gw2id",
                          description="Admin command to verify, update, or remove a user's Guild Wars 2 ID")
    @app_commands.describe(
        action="Choose 'verify', 'update', or 'remove'",
        user="The user to verify, update, or remove (@mention)",
        gw2_id="The user's GW2 ID (for verify action only)",
        id_type="The type of ID to remove (for remove action only)"
    )
    @app_commands.choices(action=[
        app_commands.Choice(name="verify", value="verify"),
        app_commands.Choice(name="update", value="update"),
        app_commands.Choice(name="remove", value="remove")
    ])
    @app_commands.choices(id_type=[
        app_commands.Choice(name="Main ID", value="main"),
        app_commands.Choice(name="Alt ID", value="alt")
    ])
    @app_commands.checks.has_any_role(ROLE_ID_STAFF)
    async def admin_gw2id(self, interaction: discord.Interaction, action: str, user: discord.Member,
                          gw2_id: str = None, id_type: str = None):

        if action == "verify":
            await interaction.response.defer(ephemeral=True)

            # Use the existing process_verification method from ConfirmationCog
            confirmation_cog = self.bot.get_cog('ConfirmationCog')
            if confirmation_cog:
                await confirmation_cog.process_verification(interaction, gw2_id, user)
            else:
                await interaction.followup.send("ConfirmationCog not found. Unable to process verification.")

        elif action == "update":
            # Trigger the update modal for the selected user
            await interaction.response.send_modal(AdminGW2IDUpdateModal(interaction, user))

        elif action == "remove":
            if id_type not in ["main", "alt"]:
                await interaction.response.send_message("Please specify if you want to remove 'main' or 'alt' ID.",
                                                        ephemeral=True)
                return

            conn = sqlite3.connect(CURRENT_DB_FILENAME)
            c = conn.cursor()

            try:
                # Remove based on id_type (main or alt)
                if id_type == "main":
                    c.execute("UPDATE users SET gw2_id = '-', guild_status = '-' WHERE discord_id = ?", (str(user.id),))
                    message = "Main Guild Wars 2 ID has been removed."
                elif id_type == "alt":
                    c.execute("UPDATE users SET alt_gw2_id = '-', alt_guild_status = '-' WHERE discord_id = ?",
                              (str(user.id),))
                    message = "Alt Guild Wars 2 ID has been removed."

                conn.commit()

                await interaction.response.send_message(message, ephemeral=True)
            except sqlite3.Error as e:
                await interaction.response.send_message(f"An error occurred while removing the ID: {e}", ephemeral=True)
            finally:
                conn.close()

    @admin_gw2id.error
    async def admin_gw2id_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.errors.MissingRole):
            await interaction.response.send_message("You must be an admin to use this command.", ephemeral=True)
        else:
            await interaction.response.send_message(f"An error occurred: {str(error)}", ephemeral=True)

    @app_commands.command(name="ban", description="Ban a user or view the ban list")
    @app_commands.describe(
        action="Choose whether to ban a user or view the ban list",
        user="The user to ban or view info for (ID or @mention)",
        reason="The reason for the ban (required when banning)"
    )
    @app_commands.choices(action=[
        app_commands.Choice(name="Ban User", value="ban"),
        app_commands.Choice(name="View Ban List", value="list")
    ])
    @app_commands.checks.has_any_role(ROLE_ID_STAFF)
    async def ban(self, interaction: discord.Interaction, action: str, user: str = None, reason: str = None):
        await interaction.response.defer(ephemeral=True)

        if action == "ban":
            if not user or not reason:
                await interaction.followup.send("Both user and reason are required when banning a user.",
                                                ephemeral=True)
                return

            # Try to find the user by Discord ID/mention
            if user.startswith('<@') and user.endswith('>'):
                discord_id = user[2:-1]
                if discord_id.startswith('!'):
                    discord_id = discord_id[1:]
            else:
                discord_id = user

            try:
                # Convert discord_id to int and get the user object
                discord_id = int(discord_id)
                user_to_ban = await interaction.guild.fetch_member(discord_id)

                # Update the database
                conn = sqlite3.connect(CURRENT_DB_FILENAME)
                c = conn.cursor()
                c.execute("INSERT OR REPLACE INTO bans (discord_id, reason, date) VALUES (?, ?, ?)",
                          (discord_id, reason, datetime.now().isoformat()))
                conn.commit()
                conn.close()

                # Ban the user from the server
                await interaction.guild.ban(user_to_ban, reason=reason)

                await interaction.followup.send(
                    f"{user_to_ban.display_name} has been banned from the server. Reason: {reason}")
            except discord.NotFound:
                await interaction.followup.send("The user was not found in the server.")
            except discord.Forbidden:
                await interaction.followup.send("I do not have permission to ban this user.")
            except discord.HTTPException:
                await interaction.followup.send("An error occurred while banning the user. Please try again later.")
            except sqlite3.Error as e:
                await interaction.followup.send(f"A database error occurred: {e}")
            except ValueError:
                await interaction.followup.send("The provided identifier is not a valid user ID.")

        elif action == "list":
            def format_date(date_string):
                try:
                    date_obj = datetime.fromisoformat(date_string)
                    return date_obj.strftime("%B %d %Y at %I:%M %p")  # e.g., "July 14 2024 at 11:47 PM"
                except ValueError:
                    return "Unknown Date"

            try:
                # Fetch bans from the Discord server
                guild_bans = [ban_entry async for ban_entry in interaction.guild.bans()]

                # Fetch bans from the database
                conn = sqlite3.connect(CURRENT_DB_FILENAME)
                c = conn.cursor()
                c.execute("SELECT discord_id, reason, date FROM bans")
                db_bans = {ban[0]: ban for ban in c.fetchall()}
                conn.close()

                # If a user is specified, filter the bans
                if user:
                    try:
                        user_id = int(user)
                        filtered_bans = [ban for ban in guild_bans if ban.user.id == user_id]
                    except ValueError:
                        filtered_bans = [ban for ban in guild_bans if ban.user.name.lower() == user.lower()]

                    if not filtered_bans:
                        await interaction.followup.send(f"No ban found for the specified user: {user}", ephemeral=True)
                        return

                    guild_bans = filtered_bans

                # Combine and format the ban information
                ban_info = []
                for ban_entry in guild_bans:
                    user = ban_entry.user
                    reason = ban_entry.reason or "No reason provided"
                    db_record = db_bans.get(str(user.id))

                    if db_record:
                        date = format_date(db_record[2])
                        del db_bans[str(user.id)]
                    else:
                        date = format_date(datetime.now().isoformat())
                        with sqlite3.connect(CURRENT_DB_FILENAME) as conn:
                            c = conn.cursor()
                            c.execute("INSERT OR REPLACE INTO bans (discord_id, reason, date) VALUES (?, ?, ?)",
                                      (str(user.id), reason, datetime.now().isoformat()))

                    ban_info.append({
                        "name": f"{user.name} (ID: {user.id})",
                        "value": f"- Reason: {reason}\n- Date: {date}",
                        "inline": False
                    })

                # Sort ban_info by date in descending order
                ban_info.sort(
                    key=lambda x: datetime.strptime(x["value"].split("\n- Date: ")[1], "%B %d %Y at %I:%M %p"),
                    reverse=True)

                # Remove bans from the database that aren't in the server bans (only if not filtering)
                if not user:
                    for db_ban_id in db_bans.keys():
                        with sqlite3.connect(CURRENT_DB_FILENAME) as conn:
                            c = conn.cursor()
                            c.execute("DELETE FROM bans WHERE discord_id = ?", (db_ban_id,))

                # Create embeds
                embeds = []
                chunk_size = 10
                for i in range(0, len(ban_info), chunk_size):
                    embed = discord.Embed(title="__**Ban List**__", color=discord.Color.red())
                    for entry in ban_info[i:i + chunk_size]:
                        embed.add_field(**entry)
                    embed.set_footer(text=f"Page {len(embeds) + 1}/{-(-len(ban_info) // chunk_size)}")
                    embeds.append(embed)

                script_dir = os.path.dirname(os.path.abspath(__file__))
                thumbnail_path = os.path.join(script_dir, "pictures", "Banlist.png")

                if os.path.exists(thumbnail_path):
                    file = discord.File(thumbnail_path, filename="Banlist.png")
                    if file:
                        for embed in embeds:
                            embed.set_thumbnail(url="attachment://Banlist.png")
                else:
                    file = None
                    print(f"Thumbnail file not found at: {thumbnail_path}")

                if not embeds:
                    await interaction.followup.send("There are no banned users.", ephemeral=True)
                else:
                    paginator = Paginator(embeds)
                    await interaction.followup.send(file=file, embed=embeds[0], view=paginator, ephemeral=True)

            except discord.Forbidden:
                await interaction.followup.send("I do not have permission to view the ban list.")
            except discord.HTTPException:
                await interaction.followup.send(
                    "An error occurred while fetching the ban list. Please try again later.")
            except sqlite3.Error as e:
                await interaction.followup.send(f"A database error occurred: {e}")

    @ban.error
    async def ban_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.errors.MissingRole):
            await interaction.response.send_message(
                msg_general.invalid_permission(),
                ephemeral=True)
        elif isinstance(error, app_commands.errors.MissingRequiredArgument):
            if error.param.name == 'reason':
                await interaction.response.send_message(
                    "The reason for the ban is required. Please provide a reason.",
                    ephemeral=True)
            else:
                await interaction.response.send_message(
                    f"Missing required argument: {error.param.name}",
                    ephemeral=True)
        else:
            await interaction.response.send_message(f"An error occurred: {str(error)}", ephemeral=True)

    @app_commands.command(name="watchlist", description="Add or remove a user from the watchlist")
    @app_commands.describe(
        action="Choose whether to add or remove from the watchlist",
        identifier="The user's Discord username/mention or GW2 ID"
    )
    @app_commands.choices(action=[
        app_commands.Choice(name="Add", value="add"),
        app_commands.Choice(name="Remove", value="remove")
    ])
    @app_commands.checks.has_any_role(ROLE_ID_STAFF, ROLE_ID_FAMED_MEMBER)
    async def watchlist(self, interaction: discord.Interaction, action: str, identifier: str):
        conn = None
        try:
            conn = sqlite3.connect(CURRENT_DB_FILENAME)
            c = conn.cursor()

            # Try to find the user by Discord ID/mention
            if identifier.startswith('<@') and identifier.endswith('>'):
                discord_id = identifier.strip('<@!>')
            else:
                discord_id = identifier

            # Check if it's a Discord ID
            c.execute("SELECT * FROM users WHERE discord_id = ?", (discord_id,))
            user_data = c.fetchone()

            # If not found, try to find by GW2 ID
            if not user_data:
                c.execute("SELECT * FROM users WHERE gw2_id = ? OR alt_gw2_id = ?", (identifier, identifier))
                user_data = c.fetchone()

            if not user_data:
                await interaction.response.send_message(msg_general.user_not_found(),
                                                        ephemeral=True)
                return

            if action == "add":
                # Open the modal directly
                await interaction.response.send_modal(AddToWatchlistModal(self, user_data[0], identifier))
            elif action == "remove":
                # Check if the user is actually on the watchlist
                if user_data[5] == '-':
                    await interaction.response.send_message(
                        f"User with identifier '{identifier}' is not on the watchlist.",
                        ephemeral=True)
                    return

                # Remove the user from the watchlist by setting watchlist_reason to '-'
                c.execute('''
                    UPDATE users
                    SET watchlist_reason = '-'
                    WHERE discord_id = ?
                ''', (user_data[0],))

                conn.commit()

                await interaction.response.send_message(
                    f"User with identifier '{identifier}' has been removed from the watchlist.",
                    ephemeral=True)

        except sqlite3.Error as e:
            await interaction.response.send_message(f"An error occurred: {e}", ephemeral=True)
        finally:
            if conn:
                conn.close()

    @watchlist.error
    async def watchlist_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.errors.MissingRole):
            await interaction.response.send_message(
                msg_general.invalid_permission(),
                ephemeral=True)
        else:
            await interaction.response.send_message(f"An error occurred: {str(error)}", ephemeral=True)

    @app_commands.command(name="warning", description="Add or remove a warning for a user")
    @app_commands.describe(action="Choose whether to add or remove a warning", identifier="The user's @mention or GW2 ID", reason="The reason for the warning (only required when adding a warning)")
    @app_commands.choices(action=[app_commands.Choice(name="Add", value="add"), app_commands.Choice(name="Remove", value="remove")])
    @app_commands.checks.has_any_role(ROLE_ID_STAFF, ROLE_ID_FAMED_MEMBER)
    async def warning(self, interaction: discord.Interaction, action: str, identifier: str, reason: str = None):
        await interaction.response.defer(ephemeral=True)

        if action == "add" and not reason:
            await interaction.followup.send(msg_warning.reason_required(), ephemeral=True)
            return

        try:
            with sqlite3.connect(CURRENT_DB_FILENAME) as conn:
                c = conn.cursor()

                # Try to find the user by Discord ID/mention
                if identifier.startswith('<@') and identifier.endswith('>'):
                    discord_id = identifier.strip('<@!>')
                else:
                    discord_id = identifier

                # Check if it's a Discord ID
                c.execute("SELECT * FROM users WHERE discord_id = ?", (discord_id,))
                user_data = c.fetchone()

                # If not found, try to find by GW2 ID
                if not user_data:
                    c.execute("SELECT * FROM users WHERE gw2_id = ? OR alt_gw2_id = ?", (identifier, identifier))
                    user_data = c.fetchone()

                if not user_data:
                    await interaction.response.send_message(
                        msg_general.user_not_found(),
                        ephemeral=True)
                    return

                discord_id, gw2_id = user_data[0], user_data[1]

                if action == "add":
                    # Remove warnings older than 3 months
                    three_months_ago = (datetime.now() - timedelta(days=90)).isoformat()
                    c.execute("DELETE FROM warnings WHERE discord_id = ? AND date < ?", (discord_id, three_months_ago))

                    # Add the new warning
                    warning_date = datetime.now().isoformat()
                    c.execute("INSERT INTO warnings (discord_id, reason, date) VALUES (?, ?, ?)",
                              (discord_id, reason, warning_date))

                    # Update the warnings count in the users table
                    c.execute(
                        "UPDATE users SET warnings = (SELECT COUNT(*) FROM warnings WHERE discord_id = ?), last_warning_date = ? WHERE discord_id = ?",
                        (discord_id, warning_date, discord_id))

                    # Fetch the updated warning count
                    c.execute("SELECT warnings FROM users WHERE discord_id = ?", (discord_id,))
                    warning_count = c.fetchone()[0]

                    embed = discord.Embed(title="Warning Added", color=discord.Color.orange())
                    embed.add_field(name="User", value=f"<@{discord_id}> (GW2 ID: {gw2_id})", inline=False)
                    embed.add_field(name="Reason", value=reason, inline=False)
                    embed.add_field(name="Date",
                                    value=datetime.fromisoformat(warning_date).strftime("%Y-%m-%d %H:%M:%S"),
                                    inline=False)
                    embed.add_field(name="Total Warnings", value=str(warning_count), inline=False)

                    await interaction.followup.send(embed=embed)

                    # Fetch the updated list of warnings (after adding the new one)
                    c.execute("SELECT * FROM warnings WHERE discord_id = ? ORDER BY date DESC", (discord_id,))
                    warnings = c.fetchall()

                    # Send a DM to the warned user based on warning count
                    try:
                        user = await interaction.client.fetch_user(int(discord_id))
                        if warning_count == 1:
                            await user.send(msg_warning.first_warning(user.mention, reason, CHANNEL_ID_RULES))
                        elif warning_count == 2:
                            await user.send(msg_warning.second_warning(user.mention, reason, CHANNEL_ID_RULES))
                        else:
                            await user.send(msg_warning.third_warning(user.mention, reason, CHANNEL_ID_RULES))
                    except discord.HTTPException:
                        await interaction.followup.send(msg_warning.dm_user_error())

                    # Send a message to the Mentor's channel
                    mentor_channel = interaction.guild.get_channel(CHANNEL_ID_MENTORS)
                    if mentor_channel:
                        view = discord.ui.View()
                        view.add_item(WarningsButton(self, discord_id, warnings))  # Now warnings is initialized

                        await mentor_channel.send(
                            msg_warning.user_received_warning(discord_id, warning_count),
                            view=view
                        )
                    else:
                        await interaction.followup.send(msg_warning.notify_mentor_channel())

                elif action == "remove":
                    # Fetch warnings in ascending order (oldest first)
                    c.execute("SELECT * FROM warnings WHERE discord_id = ? ORDER BY date ASC", (discord_id,))
                    warnings = c.fetchall()

                    if not warnings:
                        await interaction.followup.send(msg_warning.no_warnings(), ephemeral=True)
                        return

                    # Display warnings using the new method (which should display oldest to newest)
                    await display_warnings(interaction, discord_id, warnings)

                    # Ask which warning to remove
                    await interaction.followup.send(msg_warning.warning_remove_number(), ephemeral=True)

                    def check(m):
                        return m.author == interaction.user and m.channel == interaction.channel and m.content.isdigit()

                    try:
                        msg = await interaction.client.wait_for('message', check=check, timeout=30.0)

                    except asyncio.TimeoutError:

                        await interaction.followup.send(msg_general.no_response(), ephemeral=True)
                        return

                    warning_number = int(msg.content)
                    await msg.delete()  # Delete the user's input message

                    if warning_number < 1 or warning_number > len(warnings):
                        await interaction.followup.send(msg_warning.invalid_warning_number(), ephemeral=True)
                        return

                    # Remove the selected warning
                    warning_to_remove = warnings[warning_number - 1]

                    c.execute("DELETE FROM warnings WHERE discord_id = ? AND date = ?", (discord_id, warning_to_remove[3]))

                    # Update the warnings count in the users table
                    c.execute("UPDATE users SET warnings = warnings - 1 WHERE discord_id = ?", (discord_id,))
                    conn.commit()
                    await interaction.followup.send(msg_warning.warning_removed(warning_number), ephemeral=True)

                    # Display updated warnings
                    c.execute("SELECT * FROM warnings WHERE discord_id = ? ORDER BY date ASC", (discord_id,))
                    updated_warnings = c.fetchall()

                    await self.display_warnings(interaction, discord_id, updated_warnings)

        except sqlite3.Error as e:
            await interaction.followup.send(f"A database error occurred: {e}", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"An unexpected error occurred: {e}", ephemeral=True)

    @warning.error
    async def warning_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.errors.MissingRole):
            await interaction.response.send_message(
                msg_general.invalid_permission(),
                ephemeral=True)
        else:
            await interaction.response.send_message(f"An error occurred: {str(error)}", ephemeral=True)

    @app_commands.command(name="get-applications", description="View staff member applications")
    @app_commands.checks.has_any_role(ROLE_ID_STAFF)
    async def get_applications(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        conn = None
        try:
            conn = sqlite3.connect(CURRENT_DB_FILENAME)
            c = conn.cursor()

            # Fetch all applications, ordered by most recent first
            c.execute("SELECT id, timestamp, discord_id, gw2_id FROM mentor_applications ORDER BY id DESC")
            applications = c.fetchall()

            if not applications:
                await interaction.followup.send("There are no pending applications.", ephemeral=True)
                return

            # Create the initial embed with the list of applications
            embed = discord.Embed(title="Staff Member Applications", color=discord.Color.blue())
            for app in applications:
                embed.add_field(
                    name=f"Application ID: {app[0]}",
                    value=f"Date: {app[1]}\nDiscord: <@{app[2]}>\nGW2 ID: {app[3]}",
                    inline=False
                )

            # Set thumbnail
            script_dir = os.path.dirname(os.path.abspath(__file__))
            thumbnail_path = os.path.join(script_dir, "pictures", "Application.png")

            if os.path.exists(thumbnail_path):
                file = discord.File(thumbnail_path, filename="Application.png")
                embed.set_thumbnail(url="attachment://Application.png")
            else:
                file = None
                print(f"Thumbnail file not found at: {thumbnail_path}")

            view = ApplicationView(bot=self.bot)
            await interaction.followup.send(file=file, embed=embed, view=view, ephemeral=True)

        except sqlite3.Error as e:
            await interaction.followup.send(f"A database error occurred: {e}", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"An unexpected error occurred: {e}", ephemeral=True)
        finally:
            if conn:
                conn.close()

    @get_applications.error
    async def get_applications_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.errors.MissingRole):
            await interaction.response.send_message(
                msg_general.invalid_permission(),
                ephemeral=True)
        else:
            await interaction.response.send_message(f"An error occurred: {str(error)}", ephemeral=True)

    @app_commands.command(name="crosscheck", description="Check the guild roster for members without linked Discord accounts.")
    @app_commands.checks.has_any_role(ROLE_ID_STAFF, ROLE_ID_FAMED_MEMBER)
    async def crosscheck(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        try:
            # Fetch the guild roster from the GW2 API
            response = requests.get(f"https://api.guildwars2.com/v2/guild/{GUILD_ID}/members",
                                    headers={"Authorization": f"Bearer {API_KEY}"})
            if response.status_code != 200:
                await interaction.followup.send("Failed to fetch the guild roster. Please try again later.",
                                                ephemeral=True)
                return
            guild_roster = response.json()

            # Fetch the user database (Discord users linked to GW2 accounts)
            conn = sqlite3.connect(CURRENT_DB_FILENAME)
            c = conn.cursor()
            c.execute("SELECT gw2_id, alt_gw2_id, discord_id FROM users")
            user_links = c.fetchall()
            conn.close()

            # Create a set of all linked GW2 IDs (both main and alt)
            linked_gw2_ids = {main_id for main_id, alt_id, _ in user_links}
            linked_gw2_ids.update(alt_id for _, alt_id, _ in user_links if alt_id)

            # Find unlinked members
            unlinked_members = [
                member for member in guild_roster
                if member['name'] not in linked_gw2_ids and member.get('rank') != "Legacy Member"
            ]

            if not unlinked_members:
                await interaction.followup.send("All guild members have linked Discord accounts.", ephemeral=True)
                return

            # Create embeds
            embeds = []
            chunk_size = 10
            for i in range(0, len(unlinked_members), chunk_size):
                embed = discord.Embed(title="Guild Members Without Linked Discord Accounts",
                                      color=discord.Color.orange())

                for member in unlinked_members[i:i + chunk_size]:
                    embed.add_field(
                        name=f"**{member['name']}** *({member['rank']})*",
                        value="\u200b",  # Zero-width space
                        inline=False
                    )

                # Add the message block
                message_block = msg_cross_check(DISCORD_INVITE_URL)
                embed.add_field(name="Message Template", value=message_block, inline=False)

                embed.set_footer(text=f"Page {len(embeds) + 1}/{-(-len(unlinked_members) // chunk_size)}")
                embeds.append(embed)

            # Add server icon as thumbnail to all embeds
            if interaction.guild and interaction.guild.icon:
                for embed in embeds:
                    embed.set_thumbnail(url=interaction.guild.icon.url)

            # Send the embeds with the paginator
            paginator = Paginator(embeds)
            await interaction.followup.send(embed=embeds[0], view=paginator, ephemeral=True)

        except requests.RequestException as e:
            await interaction.followup.send(f"Network error occurred: {str(e)}", ephemeral=True)
        except sqlite3.Error as e:
            await interaction.followup.send(f"Database error occurred: {str(e)}", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"An unexpected error occurred: {str(e)}", ephemeral=True)

    @crosscheck.error
    async def crosscheck_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.errors.MissingRole):
            await interaction.response.send_message(
                msg_general.invalid_permission(),
                ephemeral=True)
        else:
            await interaction.response.send_message(f"An error occurred: {str(error)}", ephemeral=True)


# Setup function to add cogs
async def setup(bot: commands.Bot):
    await bot.add_cog(ConfirmationCog(bot))
    await bot.add_cog(MemberCog(bot))
    await bot.add_cog(StaffCog(bot))
