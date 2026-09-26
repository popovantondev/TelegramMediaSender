# Connect Telegram

The app uses Telegram's MTProto API through Telethon. It does not ask you to provide a bot token; use your own Telegram account and your own API credentials.

## Create your API credentials

1. Open [my.telegram.org](https://my.telegram.org) and sign in with your Telegram phone number.
2. Open **API development tools** and create an application entry.
3. Copy the numeric **api_id** and the **api_hash**. Telegram describes this process in its [official API ID guide](https://core.telegram.org/api/obtaining_api_id).
4. In Telegram Media Sender, choose **Profiles… → Add…**, give the profile a recognizable name, and enter your phone number, API ID, and API Hash.

Keep the API Hash private. The app stores it locally with the profile. Do not paste it into chats, issue trackers, or screenshots.

## Sign in

1. Select the profile and click **Refresh** to load chats.
2. Enter the login code that Telegram sends to an already signed-in Telegram device (or by another method Telegram offers for your account).
3. If two-step verification is enabled, enter that password when prompted.
4. Select a chat and send a small, intended group only after checking the destination.

Telethon's [sign-in documentation](https://docs.telethon.dev/en/stable/basic/signing-in.html) explains the code and optional password flow. The app saves the authorized session locally so it does not need to request the code on every launch. Telethon documents that a session contains authorization material and must be kept private in its [session guide](https://docs.telethon.dev/en/stable/concepts/sessions.html).

## If you need to revoke access

In Telegram, open **Settings → Devices** (the label may differ by platform) and terminate the session for this app. If you no longer need the profile, choose **Profiles… → Delete…**. This removes only the new app's profile and local session; profiles in the earlier app, Telegram messages, and source media remain. Removing a local session alone does not revoke a copy made elsewhere.
