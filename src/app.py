# ---------------------------------------------------------------------------------------

# Textual for TUI
# Print to console
import logging

from textual import events, keys
from textual.app import App, ComposeResult
from textual.containers import Center, Horizontal, Vertical, VerticalScroll
from textual.events import Focus, Key
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Static

logging.basicConfig(
    level=logging.DEBUG,
    filename="debug.log",
    format="%(asctime)s %(message)s ",
    datefmt="%H:%M:%S %d/%m/%Y",
)

import asyncio

import protocol
from client import Client
from datasync import DataUpdated

MOD_CODE = "[TUI] "

# ---------------------------------------------------------------------------------------

client = None

# ---------------------------------------------------------------------------------------


def get_messages_for_group(group_id):
    events = client.AppState["events"]
    groupchat = []
    logging.debug(MOD_CODE + f"[~] Retrieved {len(events)} events.")
    for event in events:
        if event.groupID == group_id:
            if isinstance(event, protocol.MessageEvent):
                groupchat.append(f"{event.senderUserID}: {event.message}")
        # return [
    #    f"[{from_user}] {content}\n" * 100
    #    for g_id, from_user, content in messages
    #    if g_id == group_id
    # ]
    if len(groupchat) == 0:
        return "No messages for this group."
    return "\n".join(groupchat)


# ---------------------------------------------------------------------------------------

# Login Modal


class LoginModal(ModalScreen):
    CSS = """
    LoginModal {
        align: center middle;
    }

    #login-box {
        width: 50;
        height: auto;
        border: round #A9B665;
        background: #1d2021;
        padding: 1 2;
    }

    #login-title {
        text-style: bold;
        color: #A9B665;
        margin-bottom: 1;
    }

    .login-input {
        margin-bottom: 1;
    }

    #login-submit {
        width: 100%;
        margin-top: 1;
    }
    """

    def __init__(self, user_interface) -> None:
        super().__init__()
        self.user_interface = user_interface

    def compose(self) -> ComposeResult:
        with Vertical(id="login-box"):
            yield Label("Login", id="login-title")
            yield Input(
                placeholder="Server IP", id="login-server-ip", classes="login-input"
            )
            yield Input(
                placeholder="Username", id="login-username", classes="login-input"
            )
            # TODO Password for security
            # yield Input(placeholder="Password", password=True, id="login-password", classes="login-input")
            yield Button("Submit", id="login-submit")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        username = self.query_one("#login-username", Input).value
        server_ip = self.query_one("#login-server-ip", Input).value
        logging.debug(MOD_CODE + f"[+] Logging in as user {username} to ")
        # password = self.query_one("#login-password", Input).value

        global client
        client = Client(ui=self.user_interface, server_ip=server_ip)
        login_status = await client.login(username)
        if login_status:
            self.app.post_message(DataUpdated())
            logging.debug(MOD_CODE + f"[*] Login status: {login_status}")
            logging.debug(MOD_CODE + f"[*] Calling data update")
        self.dismiss()

    def on_key(self, event: Key) -> None:
        pass  # Disable escape — user must submit to proceed


# ---------------------------------------------------------------------------------------

# Popup Action Modal

ACTION_CONFIG = {
    "action-send-file": ("Send File", "File Path", "Description"),
    "action-create-group": ("Create Group", "Group Name", "Users"),
    "action-edit-group": ("Edit Group", "Group Description", "Users"),
}


class ActionModal(ModalScreen):
    CSS = """
    ActionModal {
        align: center middle;
    }

    #modal-box {
        width: 50;
        height: auto;
        border: round #A9B665;
        background: #1d2021;
        padding: 1 2;
    }

    #modal-title {
        text-style: bold;
        color: #A9B665;
        margin-bottom: 1;
    }

    .modal-input {
        margin-bottom: 1;
    }

    #modal-submit {
        width: 100%;
        margin-top: 1;
    }
    """

    def __init__(self, title: str, field1: str, field2: str) -> None:
        super().__init__()
        self._title = title
        self._field1 = field1
        self._field2 = field2

    def compose(self) -> ComposeResult:
        with Vertical(id="modal-box"):
            yield Label(self._title, id="modal-title")
            yield Input(placeholder=self._field1, id="input-1", classes="modal-input")
            yield Input(placeholder=self._field2, id="input-2", classes="modal-input")
            yield Button("Submit", id="modal-submit")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()

        logging.debug(MOD_CODE + f"[+] Modal submitted for {self._title}.")

        match self._title:
            case "Send File":
                logging.debug(MOD_CODE + "[*] Sharing file.")
            case "Create Group":
                logging.debug(MOD_CODE + "[*] Creating group.")
                group_name = self.query_one("#input-1", Input).value
                group_members = (self.query_one("#input-2", Input).value).split(",")
                await client.create_group(group_name, group_members)
            case "Edit Group":
                logging.debug(MOD_CODE + "[*] Editting group.")

        self.dismiss()

    def on_key(self, event: Key) -> None:
        if event.key == "escape":
            self.dismiss()


# ---------------------------------------------------------------------------------------

# ---------------------------------------------------------------------------------------

# Main View


class ChatInterface(App):
    CSS = """
    Screen {
        layout: horizontal;
    }

    #left-pane {
        width: 1fr;
        border: round #D3869B;
    }

    #right-pane {
        width: 2fr;
        border: round #7DAEA3;
        layout: vertical;
    }

    #group-banner {
        height: 1;
        padding: 0 1;
        background: #2d3b3b;
        color: #7DAEA3;
        text-style: bold;
        width: 100%;
    }

    #message-scroll {
        height: 1fr;
    }

    #message-input {
        height: auto;
        dock: bottom;
        border: round #89B482;
    }

    #action-pane {
        width: 0.25fr;
        border: round #A9B665;
        layout: vertical;
        align: center bottom;
        padding: 0 0 1 0;
    }

    .action-btn {
        /*width: 3;
        height: 2;*/
        min-width: 3;
        text-align: center;
        margin: 0 0 1 0;
    }

    Button {
        width: 100%;
        text-align: left;
    }

    .selected {
        background: #443840;
    }
    """

    def compose(self) -> ComposeResult:
        self.message_input = MessageInput(self)

        with Horizontal():
            with VerticalScroll(id="left-pane"):
                self.message_display = Static("Join/create a group.")
                yield self.message_display
            with Vertical(id="right-pane"):
                yield Static("", id="group-banner")
                with VerticalScroll(id="message-scroll"):
                    self.message_display = Static("Select a group to see messages.")
                    yield self.message_display
                yield self.message_input

            with Vertical(id="action-pane"):
                yield Button("Share File", id="action-send-file", classes="action-btn")
                yield Button(
                    "Create Group", id="action-create-group", classes="action-btn"
                )
                yield Button("Edit Group", id="action-edit-group", classes="action-btn")

        self.current_pane = "left"
        self.selected_button = 0
        self.selected_action = 0
        self.action_ids = [
            "action-send-file",
            "action-create-group",
            "action-edit-group",
        ]

    async def on_focus(self, event: events.Focus) -> None:
        logging.debug(MOD_CODE + "Focused event.")
        if event.control == self.query_one("#message-input", Input)._get_dom_base:
            logging.debug(MOD_CODE + "On mesage input.")
            self.current_pane = "right"

        return await super().on_event(event)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id

        # TODO fix modal inputs
        if btn_id in ACTION_CONFIG:
            title, field1, field2 = ACTION_CONFIG[btn_id]
            self.app.push_screen(ActionModal(title, field1, field2))

        else:
            group_id = int(btn_id.split("-")[1])
            self.current_group = group_id

            group_name = group_id

            self.query_one("#group-banner", Static).update(f" {group_name}")

            group_buttons = [
                b for b in self.query(Button) if b.id and b.id.startswith("group-")
            ]
            for idx, button in enumerate(group_buttons):
                button.remove_class("selected")
                if button.id == btn_id:
                    button.add_class("selected")
                    button.focus()
                    self.current_pane = "left"

            group_messages = get_messages_for_group(group_id)
            self.message_display.update(group_messages)

            scroll = self.query_one("#message-scroll", VerticalScroll)
            self.call_after_refresh(scroll.scroll_end, animate=False)

    # Handle key press events for navigation
    async def on_key(self, event: Key) -> None:
        if event.key == "right" and self.current_pane == "left":
            self.current_pane = "right"
            self.update_pane_selection()

        elif event.key == "left" and self.current_pane == "right":
            self.current_pane = "left"
            self.update_pane_selection()

        elif event.key == "right" and self.current_pane == "right":
            self.current_pane = "action"
            self.update_pane_selection()

        elif event.key == "left" and self.current_pane == "action":
            self.current_pane = "right"
            self.update_pane_selection()

        elif event.key == "down" and self.current_pane == "action":
            self.selected_action = min(
                self.selected_action + 1, len(self.action_ids) - 1
            )
            self.update_pane_selection()
            event.prevent_default()

        elif event.key == "up" and self.current_pane == "action":
            self.selected_action = max(self.selected_action - 1, 0)
            self.update_pane_selection()
            event.prevent_default()

        elif event.key == "down" and self.current_pane == "left":
            self.selected_button = min(self.selected_button + 1, len(self.groups) - 1)
            self.update_pane_selection()

        elif event.key == "up" and self.current_pane == "left":
            self.selected_button = max(self.selected_button - 1, 0)
            self.update_pane_selection()

        elif event.key == "down" and self.current_pane == "right":
            self.query_one("#message-scroll", VerticalScroll).scroll_down()
            event.prevent_default()

        elif event.key == "up" and self.current_pane == "right":
            self.query_one("#message-scroll", VerticalScroll).scroll_up()
            event.prevent_default()

    # Update the selection based on the current pane
    def update_pane_selection(self):
        if self.current_pane == "left":
            group_buttons = [
                b for b in self.query(Button) if b.id and b.id.startswith("group-")
            ]
            for idx, button in enumerate(group_buttons):
                button.remove_class("selected")
                if idx == self.selected_button:
                    group_id = int(button.id.split("-")[1])
                    self.current_group = group_id
                    button.add_class("selected")
                    button.focus()
        elif self.current_pane == "right":
            self.query_one("#message-input", Input).focus()
        elif self.current_pane == "action":
            action_buttons = [
                b for b in self.query(Button) if b.id and b.id.startswith("action-")
            ]
            for idx, button in enumerate(action_buttons):
                button.remove_class("selected")
                if idx == self.selected_action:
                    button.add_class("selected")
                    button.focus()

    def on_mount(self) -> None:
        self.push_screen(LoginModal(self))

    async def update_groups(self, new_groups):
        self.groups = new_groups
        logging.debug(MOD_CODE + f"[~] New groups are {self.groups}")
        left_pane = self.query_one("#left-pane", VerticalScroll)
        await left_pane.remove_children()
        if len(self.groups) > 0:
            for group_id, group_data in self.groups.items():
                group_id = group_data["group_id"]
                group_name = group_data["group_name"]
                members = group_data["members"]
                left_pane.mount(Button(group_name, id=f"group-{group_id}"))
        else:
            left_pane.mount(Static("Join/create a group."))

    async def on_data_updated(self, message: DataUpdated) -> None:
        logging.debug(MOD_CODE + f"[*] Invoking data update in chat interface.")
        await self.update_groups(client.AppState["groups"])
        if hasattr(self, "current_group"):
            group_messages = get_messages_for_group(self.current_group)
            self.message_display.update(group_messages)
            scroll = self.query_one("#message-scroll", VerticalScroll)
            self.call_after_refresh(scroll.scroll_end, animate=False)


class MessageInput(Input):
    def __init__(self, app: ChatInterface) -> None:
        self.chat_interface = app
        super().__init__(placeholder="Type a message...", id="message-input")

    async def on_key(self, event: Key) -> None:
        if event.key == "enter":
            message = self.value
            if len(message) > 0:
                logging.debug(MOD_CODE + f"[*] Send message ({message}) requested.")
                await client.send_message(self.chat_interface.current_group, message)
                self.clear()
            event.prevent_default()


if __name__ == "__main__":
    ChatInterface().run()
