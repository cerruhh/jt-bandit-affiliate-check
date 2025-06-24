from http.client import responses

import discord
import pandas.errors
from discord import app_commands

import requests
import json
import asyncio
import csv
import os
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


async def save_csv(steam_id: str, interaction: discord.Interaction, debug_mode: bool = False):
    if os.path.exists(CSV_FILE):
        df = pd.read_csv(CSV_FILE)
    else:
        df = pd.DataFrame(columns=["steamid", "verified_date"])

    # Check if steamid already exists
    if steam_id not in df["steamid"].astype(str).values:
        # Append new row
        new_row = {
            "steamid": steam_id,
            "verified_date": datetime.datetime.now().strftime("%Y-%m-%d"),
            "discord_id": str(interaction.user.id)
        }
        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
        df.to_csv(CSV_FILE, index=False)
        if debug_mode:
            await interaction.channel.send(f"Added SteamID64 {steam_id} to savedata.csv with verification date.")
    else:
        await interaction.channel.send(f"SteamID {steam_id} already in savedata.csv.")


async def award_role(interaction: discord.Interaction):
    role = interaction.guild.get_role(role_id)
    if interaction.guild.me.top_role <= interaction.user.top_role or interaction.user.resolved_permissions.administrator == True:
        await interaction.channel.send("Cannot remove role from a user with higher permissions")
        return

    if not interaction.guild.me.guild_permissions.manage_roles:
        await interaction.channel.send("I do not have the manage roles permission, exiting command.")
        return

    if role is None:
        await interaction.channel.send("Role not found!")
        return

    await interaction.user.add_roles(role)
    await interaction.channel.send("Verified!")


async def remove_role(user_id: int, interaction: discord.Interaction):
    user = await interaction.guild.fetch_member(user_id)
    if interaction.guild.me.top_role <= interaction.user.top_role or interaction.user.resolved_permissions.administrator == True:
        await interaction.channel.send("Cannot remove role from a user with higher permissions")
        return

    if not interaction.guild.me.guild_permissions.manage_roles:
        await interaction.channel.send("I do not have the manage roles permission, exiting command.")
        return

    role = interaction.guild.get_role(role_id)
    if role is None:
        await interaction.channel.send("Role not found!")
        return

    await user.remove_roles(role)
    return


async def send_request(steam_id: str):
    parameters: dict = {
        "steamid": steam_id,
    }
    headers = {
        "Authorization": f"Bearer {bkey}"
    }

    response = requests.request("GET", url=URL,
                                params=parameters, data={}, headers=headers)
    return response


@client.tree.command()
@app_commands.describe(steam_id="Your SteamID64")
async def verify(interaction: discord.Interaction, steam_id_64: str, debug_mode: bool = False):
    if not interaction.user.resolved_permissions.administrator and debug_mode:
        await interaction.response.send_message("You need to be an administrator to use debug mode!")
        return

    role = interaction.guild.get_role(role_id)

    if role in interaction.user.roles:
        await interaction.response.send_message("User is already verified!")
        return

    if os.path.isfile(path=CSV_FILE):
        try:
            dataframe = pd.read_csv("savedata.csv")
            if interaction.user.id in dataframe["discord_id"].values:
                await award_role(interaction=interaction)
                await interaction.response.send_message("Adding missing role to your user...")
                return
        except pandas.errors.EmptyDataError:
            print("Empty data warning!")

    if debug_mode:
        await interaction.channel.send(f"Got id: {steam_id_64}")

    # Send the response
    response = await send_request(steam_id=steam_id_64)

    # Debug data
    if debug_mode:
        await interaction.channel.send(f"""SEND_URL: {URL}
    METHOD: GET
    """)
        await interaction.channel.send(f"RESPONSE: {response.content}")

        if URL == "https://api.bandit.camp/affiliates/is-affiliate":
            await interaction.channel.send(f"IS-AFFIL: {response.json()["response"]}")

    is_affiliate = response.json()["response"]

    if URL == "https://api.bandit.camp/affiliates/is-affiliate":
        await interaction.channel.send(f"Steam Userid {steam_id_64} is {'' if is_affiliate else 'not '}an affiliate!")

        if is_affiliate or debug_mode:
            if debug_mode:
                await interaction.channel.send("Saving anyway...")
            print("Setting data!")
            await save_csv(steam_id=steam_id_64, interaction=interaction, debug_mode=debug_mode)
            await award_role(interaction=interaction)


@client.tree.command()
@app_commands.default_permissions(administrator=True)
async def update(interaction: discord.Interaction):
    if not os.path.isfile(path=CSV_FILE):
        await interaction.response.send_message("No savedata saved!")
        return

    dataframe = pd.read_csv("savedata.csv")

    # Record the amount of people no longer affilated
    amount_of_users_dropped = 0
    for index, row in dataframe.iterrows():
        user_check_response = await send_request(steam_id=row["steamid"])

        # No longer affiliated
        if not user_check_response.json()["response"]:
            dc_id: int = int(row["discord_id"])

            # Remove from dataframe!
            dataframe.drop(index=index, inplace=True)
            if interaction.guild.fetch_member(dc_id) in interaction.guild.members:
                await remove_role(interaction=interaction, user_id=dc_id)
            amount_of_users_dropped += 1

    if amount_of_users_dropped == 0:
        await interaction.channel.send(
            f"{amount_of_users_dropped} dropped from affiliation role, savedata not written!")
    else:
        dataframe.to_csv(path_or_buf=CSV_FILE)
        await interaction.channel.send(f"{amount_of_users_dropped} dropped from affiliation role, savedata written!")


client.run(token=token)
