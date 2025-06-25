import re

import discord
from discord import app_commands
import requests
import json
import asyncio
import datetime
import sqlite3

# Init the token
with open("config_secrets.json", mode="r") as file:
    json_open = json.load(file)
    token = json_open["token"]
    my_guild = json_open["guild_id"]
    bkey = json_open["bkey"]
    role_id = json_open["role-id"]

MG_GUILD = discord.Object(id=int(my_guild))
URL = "https://api.bandit.camp/affiliates/is-affiliate"
GET_USER_STATS_URL = "https://api.bandit.camp/affiliates/user-stats"
# ?steamid=76561198834014794&start=2024-10-01&end=2024-11-01

# Database
SQLITE_DB = "savedata.db"
TABLE_NAME = "affiliates"


def init_db():
    conn = sqlite3.connect(SQLITE_DB)
    c = conn.cursor()
    c.execute(f"""
        CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
            steamid TEXT PRIMARY KEY,
            verified_date TEXT,
            discord_id TEXT
        )
    """)
    conn.commit()
    conn.close()


async def save_sqlite(steam_id: str, interaction: discord.Interaction, debug_mode: bool = False):
    conn = sqlite3.connect(SQLITE_DB)
    c = conn.cursor()
    c.execute(f"SELECT 1 FROM {TABLE_NAME} WHERE steamid = ?", (steam_id,))
    exists = c.fetchone()
    if not exists:
        c.execute(f"INSERT INTO {TABLE_NAME} (steamid, verified_date, discord_id) VALUES (?, ?, ?)",
                  (steam_id, datetime.datetime.now().strftime("%Y-%m-%d"), str(interaction.user.id)))
        conn.commit()
        if debug_mode:
            await interaction.channel.send(f"Added SteamID64 {steam_id} to database with verification date.")
    else:
        await interaction.channel.send(f"SteamID {steam_id} already in database.")
    conn.close()


init_db()


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


async def filter_steam_uri(uri: str) -> str:
    match = re.search(r"steamcommunity\.com/profiles/(\d+)", uri)
    if match:
        steamid64 = match.group(1)
        return steamid64
    return "e2"

async def request_user_stats(steam_id: str):
    now_datetime = datetime.datetime.now()
    future_date = now_datetime + datetime.timedelta(days=30)

    parameters: dict = {
        "steamid": steam_id,
        "start": now_datetime.strftime("%Y-%m-%d"),
        "end": future_date.strftime("%Y-%m-%d")
    }
    # ?steamid=76561198834014794&start=2024-10-01&end=2024-11-01
    headers = {
        "Authorization": f"Bearer {bkey}"
    }
    response = requests.request(method="GET", url=GET_USER_STATS_URL, params=parameters, headers=headers, data={})
    return response


async def award_role(interaction: discord.Interaction):
    role = interaction.guild.get_role(role_id)
    if interaction.guild.me.top_role <= interaction.user.top_role:
        await interaction.channel.send("Cannot award role to a user with higher permissions")
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
    user: discord.Member = await interaction.guild.fetch_member(user_id)
    if user is None:
        await interaction.channel.send("USER: Interaction remove_role error!")
        return

    if interaction.guild.me.top_role <= user.top_role:
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
@app_commands.describe(steam_id_64="Your SteamID64")
async def verify(interaction: discord.Interaction, steam_id_64: str, debug_mode: bool = False):
    if not interaction.user.resolved_permissions.administrator and debug_mode:
        await interaction.response.send_message("You need to be an administrator to use debug mode!")
        return

    role = interaction.guild.get_role(role_id)

    if role in interaction.user.roles:
        await interaction.response.send_message("User is already verified!")
        return

    # if os.path.isfile(path=SQLITE_DB):
    #     try:
    #         dataframe = pd.read_csv("savedata.csv")
    #         if interaction.user.id in dataframe["discord_id"].values:
    #             await award_role(interaction=interaction)
    #             await interaction.response.send_message("Adding missing role to your user...")
    #             return
    #     except pandas.errors.EmptyDataError:
    #         print("Empty data warning!")

    if debug_mode:
        await interaction.channel.send(f"Got id: {steam_id_64}")

    if "steamcommunity.com" in steam_id_64:
        steam_id_64 = await filter_steam_uri(steam_id_64)
        if steam_id_64 == "e2":
            await interaction.response.send_message(
                "This steamcommunity link is not valid. try to enter a steamid64 instead if the issue persists.")
            return

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
            await save_sqlite(steam_id=steam_id_64, interaction=interaction, debug_mode=debug_mode)
            await award_role(interaction=interaction)


@client.tree.command()
@app_commands.default_permissions(administrator=True)
async def update(interaction: discord.Interaction):
    conn = sqlite3.connect(SQLITE_DB)
    c = conn.cursor()
    c.execute(f"SELECT steamid, discord_id FROM {TABLE_NAME}")
    rows = c.fetchall()
    amount_of_users_dropped = 0
    for steamid, discord_id in rows:
        user_check_response = await send_request(steam_id=steamid)
        if not user_check_response.json()["response"]:
            # Remove from DB
            c.execute(f"DELETE FROM {TABLE_NAME} WHERE steamid = ?", (steamid,))
            try:
                if await interaction.guild.fetch_member(int(discord_id)):
                    await remove_role(interaction=interaction, user_id=int(discord_id))
            except Exception:
                pass
            amount_of_users_dropped += 1
    conn.commit()
    conn.close()
    if amount_of_users_dropped == 0:
        await interaction.response.send_message(
            f"{amount_of_users_dropped} dropped from affiliation role, database not written!")
    else:
        await interaction.response.send_message(
            f"{amount_of_users_dropped} dropped from affiliation role, database updated!")


@client.tree.command()
@app_commands.default_permissions(administrator=True)
async def list(interaction: discord.Interaction):
    conn = sqlite3.connect(SQLITE_DB)
    c = conn.cursor()
    c.execute(f"SELECT steamid, verified_date, discord_id FROM {TABLE_NAME}")
    rows = c.fetchall()
    conn.close()
    if not rows:
        await interaction.response.send_message("No savedata saved!")
        return
    lines = []
    for steamid, verified_date, discord_id in rows:
        user: discord.User = await client.fetch_user(int(discord_id))
        username = user.display_name if user else ""
        line = f"discord_id: {discord_id}, join-date: {verified_date}, steamid64: {steamid}, username: {username}"
        lines.append(line)
    result = "\n".join(lines) or "Empty."
    await interaction.response.send_message(result)


@client.tree.command()
@app_commands.default_permissions(administrator=True)
async def usercheck(interaction: discord.Interaction, steamid64: str):
    if "steamcommunity.com" in steamid64:
        steamid64 = await filter_steam_uri(steamid64)
        if steamid64 == "e2":
            await interaction.response.send_message(
                "This steamcommunity link is not valid. try to enter a steamid64 instead if the issue persists.")
            return

    use_save_data = True
    conn = sqlite3.connect(SQLITE_DB)
    c = conn.cursor()
    c.execute(f"SELECT verified_date, discord_id FROM {TABLE_NAME} WHERE steamid = ?", (steamid64,))
    row = c.fetchone()
    conn.close()


    response = await request_user_stats(steam_id=steamid64)
    rp_json: dict = response.json()["response"]

    affiliation_status = False
    affiliation_start = ""
    discord_id = "0"
    if row:
        affiliation_status = True
        affiliation_start, discord_id = row

    discord_user = None
    if discord_id != "0":
        discord_user: discord.User = await client.fetch_user(int(discord_id))
    discorduser_display_name = discord_user.display_name if discord_user else "N/A"
    discorduser_user_name = discord_user.name if discord_user else "N/A"

    response_msg = f"""Success!
Earnings: {str(rp_json["earnings"])}
Deposited: {str(rp_json["deposited"])}
Wagered: {str(rp_json["wagered"])}
Affiliated: {str(affiliation_status)}
Discord ID: {discord_id}
Discord DisplayName: {discorduser_display_name}
Discord Username: {discorduser_user_name}
Affiliation Date: {affiliation_start}
"""
    await interaction.response.send_message(response_msg)


client.run(token=token)
