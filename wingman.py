# Standard library imports
import os
import asyncio
import aiohttp

# Third-party imports
import discord
from discord.ext import commands
from discord import app_commands

# Personal files
from classes import ConfirmationCog, StaffCog
from config import TOKEN
from db import update_database, daily_update, init_db, start_daily_update, check_and_update_db, CURRENT_DB_VERSION, \
    get_db_filename

intents = discord.Intents.all()
bot = commands.Bot(command_prefix='/', intents=intents)


@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')
    try:
        if 'classes' not in bot.extensions:
            await bot.load_extension('classes')
            print("Cogs loaded successfully")
        else:
            print("Cogs already loaded")

        # Force a global sync
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} commands globally")

        print("Commands in tree after sync:")
        for command in bot.tree.get_commands():
            print(f"- {command.name}")

        # Check and update the database structure if necessary
        try:
            check_and_update_db(bot)
        except DatabaseMigrationError as e:
            print(f"Database migration failed: {e}")
            await bot.close()
            return

        await update_database(bot)  # Run update immediately when bot starts
        await asyncio.create_task(start_daily_update(bot))  # Start the daily update task with the correct delay

    except Exception as e:
        print(f"An error occurred: {e}")
        await bot.close()


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        print(f"Command not found: {ctx.message.content}")
    else:
        print(f"An error occurred: {error}")


if __name__ == "__main__":
    try:
        bot.run(TOKEN)
    except Exception as e:
        print(f"Error running the bot: {e}")
