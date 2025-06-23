import discord
from discord import app_commands

import requests
import json
import asyncio

import csv
import os

print(os.getcwd())

import datetime
import pandas as pd

# Init the token
with open("config_secrets.json", mode="r") as file:
    json_open = json.load(file)
    token = json_open["token"]
    my_guild = json_open["guild_id"]
    bkey = json_open["bkey"]
    role_id = json_open["role-id"]

MG_GUILD = discord.Object(id=int(my_guild))
URL = "https://api.bandit.camp/affiliates/is-affiliate"
STEAM_URL = "https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/"  # ?key=YOUR_API_KEY&steamids=STEAM_ID
CSV_FILE = "savedata.csv"


class MyClient(discord.Client):
    # noinspection PyShadowingNames
    def __init__(self, *, intents: discord.Intents):
        super().__init__(intents=intents)
        # A CommandTree is a special type that holds all the application command
        # state required to make it work. This is a separate class because it
        # allows all the extra state to be opt-in.
        # Whenever you want to work with application commands, your tree is used
        # to store and work with them.
        # Note: When using commands.Bot instead of discord.Client, the bot will
        # maintain its own tree instead.
        self.tree = app_commands.CommandTree(self)

    # In this basic example, we just synchronize the app commands to one guild.
    # Instead of specifying a guild to every command, we copy over our global commands instead.
    # By doing so, we don't have to wait up to an hour until they are shown to the end-user.
    async def setup_hook(self):
        # This copies the global commands over to your guild.
        self.tree.copy_global_to(guild=MG_GUILD)
        await self.tree.sync(guild=MG_GUILD)


intents = discord.Intents.default()
client = MyClient(intents=intents)


@client.event
async def on_ready():
    print(f'Logged in as {client.user} (ID: {client.user.id})')
    print('------')


async def save_csv(steam_id: str, interaction: discord.Interaction):
    if os.path.exists(CSV_FILE):
        df = pd.read_csv(CSV_FILE)
    else:
        df = pd.DataFrame(columns=["steamid", "verified_date"])

    # Check if steamid already exists
    if steam_id not in df["steamid"].astype(str).values:
        # Append new row
        new_row = {
            "steamid": steam_id,
            "verified_date": datetime.datetime.now().strftime("%Y-%m-%d")
        }
        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
        df.to_csv(CSV_FILE, index=False)
        await interaction.channel.send(f"Added SteamID {steam_id} to savedata.csv with verification date.")
    else:
        await interaction.channel.send(f"SteamID {steam_id} already in savedata.csv.")

async def award_role(interaction: discord.Interaction):
    role = interaction.guild.get_role(role_id)
    if role is None:
        await interaction.response.send_message("Role not found!")
        return

    await interaction.user.add_roles(role)
    await interaction.channel.send("Verified!")

@client.tree.command()
@app_commands.describe(steam_id="Your steamid")
async def verify(interaction: discord.Interaction, steam_id: str, debug_mode: bool = False):
    await interaction.channel.send(f"Got id: {steam_id}")
    parameters: dict = {
        "steamid": steam_id,
    }
    headers = {
        "Authorization": f"Bearer {bkey}"
    }

    response = requests.request("GET", url=URL,
                                params=parameters, data={}, headers=headers)
    if debug_mode:
        await interaction.channel.send(f"""SEND_URL: {URL}
    METHOD: GET
    HELLSPAWN1
    PARAMS: {parameters}
    """)
        await interaction.channel.send(f"RESPONSE: {response.content}")

        if URL == "https://api.bandit.camp/affiliates/is-affiliate":
            await interaction.channel.send(f"IS-AFFIL: {response.json()["response"]}")

    is_affiliate = response.json()["response"]

    if URL == "https://api.bandit.camp/affiliates/is-affiliate":
        await interaction.channel.send(f"Steam Userid {steam_id} is {'' if is_affiliate else 'not '}an affiliate!")

        if is_affiliate or debug_mode:
            await interaction.channel.send("Saving anyway...")
            print("Setting data!")
            await save_csv(steam_id=steam_id, interaction=interaction)
            await award_role(interaction=interaction)



client.run(token=token)
