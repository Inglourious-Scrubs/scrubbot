# Standard library imports
import sqlite3
import asyncio
import aiohttp
import os
import time
import shutil
from sqlite3 import Error
from datetime import datetime, timedelta

# Third-party imports
from discord.ext import tasks

# Personal files
from config import CURRENT_DB_VERSION, get_db_filename, CURRENT_DB_FILENAME, GUILD_ID, API_KEY, ROLE_ID_BIRTHDAY, CHANNEL_ID_GENERAL


def get_current_db_version():
    try:
        with open('db_version.txt', 'r') as f:
            return f.read().strip()
    except FileNotFoundError:
        return None


def set_current_db_version(version):
    with open('db_version.txt', 'w') as f:
        f.write(version)


def init_db(version, bot):
    db_filename = get_db_filename(version)
    conn = sqlite3.connect(db_filename)
    c = conn.cursor()

    # Users table
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            discord_id TEXT PRIMARY KEY,
            gw2_id TEXT NOT NULL COLLATE NOCASE DEFAULT 'Unknown',
            guild_status TEXT NOT NULL DEFAULT '-',
            alt_gw2_id TEXT NOT NULL COLLATE NOCASE DEFAULT '-',
            alt_guild_status TEXT NOT NULL DEFAULT '-',
            watchlist_reason TEXT NOT NULL DEFAULT '-',
            warnings INTEGER NOT NULL DEFAULT 0,
            last_warning_date TEXT NOT NULL DEFAULT '-',
            birthday TEXT NOT NULL DEFAULT '-'
        )
    ''')

    # Warnings table
    c.execute('''
        CREATE TABLE IF NOT EXISTS warnings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            discord_id TEXT NOT NULL,
            reason TEXT NOT NULL,
            date TEXT NOT NULL,
            FOREIGN KEY(discord_id) REFERENCES users(discord_id) ON DELETE CASCADE
        )
    ''')

    # Bans table
    c.execute('''
        CREATE TABLE IF NOT EXISTS bans (
            discord_id TEXT PRIMARY KEY,
            reason TEXT NOT NULL,
            date TEXT NOT NULL
        )
    ''')

    # Mentor applications table
    c.execute('''
        CREATE TABLE IF NOT EXISTS mentor_applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
            discord_id TEXT NOT NULL,
            gw2_id TEXT NOT NULL,
            joined_how TEXT NOT NULL,
            timezone TEXT NOT NULL,
            has_commander_tag TEXT NOT NULL,
            content_preference TEXT NOT NULL,
            has_led_event TEXT NOT NULL,
            event_interest TEXT,
            changes_suggested TEXT
        )
    ''')

    # Populate users table with current Discord members
    guild = bot.guilds[0]  # Assuming the bot is only in one server
    for member in guild.members:
        c.execute("INSERT OR IGNORE INTO users (discord_id) VALUES (?)", (str(member.id),))

    conn.commit()
    conn.close()
    print(f"Database initialized successfully: {db_filename}")


def get_common_columns(old_cursor, new_cursor, table_name):
    old_cursor.execute(f"PRAGMA table_info({table_name})")
    old_columns = set(column[1] for column in old_cursor.fetchall())

    new_cursor.execute(f"PRAGMA table_info({table_name})")
    new_columns = set(column[1] for column in new_cursor.fetchall())

    return list(old_columns.intersection(new_columns))


def migrate_data(old_version, new_version):
    old_db = get_db_filename(old_version)
    new_db = get_db_filename(new_version)

    old_conn = sqlite3.connect(old_db)
    new_conn = sqlite3.connect(new_db)
    old_cursor = old_conn.cursor()
    new_cursor = new_conn.cursor()

    try:
        # Migrate users table
        common_user_columns = get_common_columns(old_cursor, new_cursor, 'users')
        old_cursor.execute(f"SELECT {', '.join(common_user_columns)} FROM users")
        users = old_cursor.fetchall()

        for user in users:
            discord_id = user[common_user_columns.index('discord_id')]
            new_cursor.execute(f"SELECT discord_id FROM users WHERE discord_id = ?", (discord_id,))
            if new_cursor.fetchone():
                set_clause = ', '.join([f'{col} = ?' for col in common_user_columns if col != 'discord_id'])
                values = [user[common_user_columns.index(col)] for col in common_user_columns if col != 'discord_id']
                new_cursor.execute(f'''
                    UPDATE users
                    SET {set_clause}
                    WHERE discord_id = ?
                ''', values + [discord_id])

        # Migrate warnings table
        common_warning_columns = get_common_columns(old_cursor, new_cursor, 'warnings')
        for user in users:
            discord_id = user[common_user_columns.index('discord_id')]
            old_cursor.execute(f"SELECT {', '.join(common_warning_columns)} FROM warnings WHERE discord_id = ?",
                               (discord_id,))
            warnings = old_cursor.fetchall()
            for warning in warnings:
                placeholders = ', '.join(['?' for _ in common_warning_columns])
                new_cursor.execute(f'''
                    INSERT OR REPLACE INTO warnings ({', '.join(common_warning_columns)})
                    VALUES ({placeholders})
                ''', warning)

        # Migrate other tables: bans, mentor_applications, shouts
        for table in ['bans', 'mentor_applications']:
            common_columns = get_common_columns(old_cursor, new_cursor, table)
            old_cursor.execute(f"SELECT {', '.join(common_columns)} FROM {table}")
            rows = old_cursor.fetchall()

            for row in rows:
                placeholders = ', '.join(['?' for _ in common_columns])
                new_cursor.execute(f'''
                    INSERT OR REPLACE INTO {table} ({', '.join(common_columns)})
                    VALUES ({placeholders})
                ''', row)

        new_conn.commit()
        print("Data migration completed successfully")
        return True
    except Exception as e:
        print(f"An error occurred during migration: {e}")
        new_conn.rollback()
        return False  # Handle the error, but don't delete here
    finally:
        old_conn.close()
        new_conn.close()


def check_and_update_db(bot):
    current_version = get_current_db_version()

    if not current_version:
        print("No existing database found. Initializing new database.")
        init_db(CURRENT_DB_VERSION, bot)
        set_current_db_version(CURRENT_DB_VERSION)
        return

    if current_version != CURRENT_DB_VERSION:
        print(f"Database structure update required. Current version: {current_version}, Latest version: {CURRENT_DB_VERSION}")

        # Initialize the new database
        new_db_filename = get_db_filename(CURRENT_DB_VERSION)
        init_db(CURRENT_DB_VERSION, bot)

        try:
            # Perform data migration
            if migrate_data(current_version, CURRENT_DB_VERSION):
                # Update the version file only if migration was successful
                set_current_db_version(CURRENT_DB_VERSION)
                print("Database structure update completed successfully")
            else:
                print("Database update failed. Reverting to previous version.")
                if os.path.exists(new_db_filename):
                    os.remove(new_db_filename)

        except Exception as e:
            print(f"Failed to update database: {e}")
            # Delete the newly created database file if migration failed
            if os.path.exists(new_db_filename):
                os.remove(new_db_filename)
            print(f"Deleted new database file: {new_db_filename}")
    else:
        print(f"Database structure is up to date (version {CURRENT_DB_VERSION})")


async def get_guild_members():
    async with aiohttp.ClientSession() as session:
        url = f"https://api.guildwars2.com/v2/guild/{GUILD_ID}/members"
        headers = {"Authorization": f"Bearer {API_KEY}"}
        async with session.get(url, headers=headers) as response:
            if response.status == 200:
                return [member['name'] for member in await response.json()]
            else:
                print(f"Failed to fetch guild members: {response.status}")
                return []


async def update_database(bot):
    print("Updating database...")
    conn = sqlite3.connect(CURRENT_DB_FILENAME)
    c = conn.cursor()

    # Get all current members from the Discord server
    guild = bot.guilds[0]  # Assuming the bot is only in one server
    current_members = set(str(member.id) for member in guild.members)

    # Get all users currently in the database
    c.execute("SELECT discord_id, gw2_id, alt_gw2_id, birthday FROM users")
    db_users = {
        row[0]: {'gw2_id': row[1], 'alt_gw2_id': row[2], 'birthday': row[3]}
        for row in c.fetchall()
    }

    # Fetch guild members from GW2 API
    guild_members = await get_guild_members()

    # Add new members to the database
    new_members = current_members - set(db_users.keys())
    for member_id in new_members:
        c.execute("INSERT INTO users (discord_id, gw2_id, birthday) VALUES (?, ?, ?)", (member_id, "Unknown", '-'))
        print(f"Added new user: {member_id}")

    # Remove members who are no longer on the server
    removed_members = set(db_users.keys()) - current_members
    for member_id in removed_members:
        c.execute("DELETE FROM users WHERE discord_id = ?", (member_id,))
        c.execute("DELETE FROM warnings WHERE discord_id = ?", (member_id,))
        print(f"Removed user: {member_id}")

    # Get the birthday role
    birthday_role = guild.get_role(ROLE_ID_BIRTHDAY)  # Use ROLE_ID_BIRTHDAY to get the role

    # Prepare a list for birthday users
    birthday_users = []

    # Update Guild Status for all users and manage birthday roles
    today = datetime.now().strftime("%d.%m")  # Format as "day.month"
    for discord_id, user_data in db_users.items():
        gw2_id = user_data['gw2_id']
        alt_gw2_id = user_data['alt_gw2_id']
        birthday = user_data['birthday']

        guild_status = "Member" if gw2_id in guild_members else "-"
        alt_guild_status = "Member" if alt_gw2_id in guild_members else "-"

        # Update user status in database
        c.execute("""
            UPDATE users
            SET guild_status = ?, alt_guild_status = ?
            WHERE discord_id = ?
        """, (guild_status, alt_guild_status, discord_id))

        # Print update details
        # print(f"Updated user {discord_id}: Guild Status: {guild_status}, Alt Guild Status: {alt_guild_status}")

        # Handle birthday role assignment and collect birthday users
        member = guild.get_member(int(discord_id))
        if member:
            if birthday != '-' and birthday:
                try:
                    # Format birthday as "day.month" and compare with today's date
                    birthday_date = datetime.strptime(birthday, "%d.%m.%Y")
                    birthday_today = birthday_date.strftime("%d.%m")

                    if birthday_today == today:
                        if birthday_role and birthday_role not in member.roles:
                            await member.add_roles(birthday_role)
                            print(f"Assigned birthday role to {discord_id}")
                        birthday_users.append(member.mention)  # Collect mentions for the announcement
                    else:
                        if birthday_role and birthday_role in member.roles:
                            await member.remove_roles(birthday_role)
                            print(f"Removed birthday role from {discord_id}")
                except ValueError as e:
                    print(f"Error parsing birthday for {discord_id}: {e}")
            else:
                # If birthday is '-' or None, ensure the role is removed
                if birthday_role and birthday_role in member.roles:
                    await member.remove_roles(birthday_role)
                    print(f"Removed birthday role from {discord_id}")

    # Send birthday announcement message if there are birthday users
    if birthday_users:
        birthday_message = f"# 🎂 *Happy Birthday!* 🎂{''.join(birthday_users)} 🎉 *Have a great day!* 🎉"

        # Send the message to general channel
        channel = guild.get_channel(CHANNEL_ID_GENERAL)  # Replace YOUR_CHANNEL_ID with the actual channel ID
        if channel:
            await channel.send(birthday_message)
            print("Sent birthday announcement.")

    conn.commit()
    conn.close()
    print("Database update completed.")


@tasks.loop(hours=24)
async def daily_update(bot):
    await update_database(bot)


async def start_daily_update(bot):
    now = datetime.now()
    next_run = now.replace(hour=1, minute=0, second=0, microsecond=0)
    if now >= next_run:
        next_run += timedelta(days=1)
    delay = (next_run - now).total_seconds()

    await asyncio.sleep(delay)
    daily_update.start(bot)
