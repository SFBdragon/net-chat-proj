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

import asyncio
from pathlib import Path

# Logging
import logging
logging.basicConfig(level=logging.DEBUG, filename="debug.log", format="%(asctime)s %(message)s ", datefmt="%H:%M:%S %d/%m/%Y",)
MOD_CODE = "[TUI] "

# Custom modules
import protocol
from client import Client
from datasync import DataUpdated

# ---------------------------------------------------------------------------------------

client = None

# ---------------------------------------------------------------------------------------

# Login Modal


class LoginModal(ModalScreen):
    CSS_PATH = str(Path(__file__).parent / "../styles/login_modal.tcss")

    def __init__(self, user_interface) -> None:
        """
        Initialize the modal for login.

        :param user_interface: Reference to chat interface to pass to client on login.
        """
        super().__init__()
        self.user_interface = user_interface

    def compose(self) -> ComposeResult:
        """
        Create login modal with inputs and submit button.
        """
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
        """
        Handles (submit) button presses.
        """
        # Prevent further propogation
        event.stop()

        # Get input values
        username = self.query_one("#login-username", Input).value
        server_ip = self.query_one("#login-server-ip", Input).value
        #password = self.query_one("#login-password", Input).value
        
        logging.debug(MOD_CODE + f"[+] Logging in as user {username} to ")

        # Initialize client and login
        global client
        client = Client(ui=self.user_interface, server_ip=server_ip)
        login_status = await client.login(username)
        if login_status:
            self.app.post_message(DataUpdated())
            logging.debug(MOD_CODE + f"[*] Login status: {login_status}")
            logging.debug(MOD_CODE + f"[*] Calling data update")
        self.dismiss()

    def on_key(self, event: Key) -> None:
        """
        Disables escaping login modal.
        """
        # User must submit to proceed.
        if event.key not in ("tab", "backspace", "enter"):
            event.stop()
            event.prevent_default()

# ---------------------------------------------------------------------------------------

# Popup Action Modal

ACTION_CONFIG = {
    "action-send-file": ("Send File", "File Path", "Description"),
    "action-create-group": ("Create Group", "Group Name", "Users"),
    "action-edit-group": ("Edit Group", "Group Description", "Users"),
}


class ActionModal(ModalScreen):
    CSS_PATH = str(Path(__file__).parent / "../styles/action_modal.tcss")

    def __init__(self, title: str, field1: str, field2: str) -> None:
        """
        Initializes action modal with specified field inputs.
        """
        super().__init__()
        self._title = title
        self._field1 = field1
        self._field2 = field2

    def compose(self) -> ComposeResult:
        """
        Creates action modal.
        """
        with Vertical(id="modal-box"):
            yield Label(self._title, id="modal-title")
            yield Input(placeholder=self._field1, id="input-1", classes="modal-input")
            yield Input(placeholder=self._field2, id="input-2", classes="modal-input")
            yield Button("Submit", id="modal-submit")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """
        Handles button presses; performs action based on modal title.
        """

        # Prevent propagation
        event.stop()

        logging.debug(MOD_CODE + f"[+] Modal submitted for {self._title}.")
        
        # Infer action from modal title
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
        """
        Handles keypresses; escape to dismiss.
        """
        if event.key == "escape":
            self.dismiss()
        # Prevent propagation.
        if event.key not in ("tab", "backspace", "enter"):
            event.stop()
            event.prevent_default()


# ---------------------------------------------------------------------------------------

# ---------------------------------------------------------------------------------------

# Main View

class ChatInterface(App):
    CSS_PATH = str(Path(__file__).parent / "../styles/chat_interface.tcss")

    def compose(self) -> ComposeResult:
        """
        Create chat interface with 3 panes.
        """
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

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """
        Handles button presses in chat interface.
        """
        btn_id = event.button.id
        
        # Infer action from button ID
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

            group_messages = self.get_messages_for_group(group_id)
            self.message_display.update(group_messages)

            scroll = self.query_one("#message-scroll", VerticalScroll)
            self.call_after_refresh(scroll.scroll_end, animate=False)

    async def on_key(self, event: Key) -> None:
        """
        Handle key press events for navigation.
        """
        match self.current_pane:

            case "left":
                if event.key == "right":
                    self.current_pane = "right"
                    self.update_pane_selection()

                elif event.key == "down":
                    self.selected_button = min(self.selected_button + 1, len(self.groups) - 1)
                    self.update_pane_selection()

                elif event.key == "up":
                    self.selected_button = max(self.selected_button - 1, 0)
                    self.update_pane_selection()

            case "right":

                if event.key == "down":
                    self.query_one("#message-scroll", VerticalScroll).scroll_down()
                    event.prevent_default()

                elif event.key == "up":
                    self.query_one("#message-scroll", VerticalScroll).scroll_up()
                    event.prevent_default()

                elif event.key == "left":
                    self.current_pane = "left"
                    self.update_pane_selection()

                elif event.key == "right":
                    self.current_pane = "action"
                    self.update_pane_selection()

            case "action":

                if event.key == "left":
                    self.current_pane = "right"
                    self.update_pane_selection()

                elif event.key == "down":
                    self.selected_action = min(self.selected_action + 1, len(self.action_ids) - 1)
                    self.update_pane_selection()
                    event.prevent_default()

                elif event.key == "up":
                    self.selected_action = max(self.selected_action - 1, 0)
                    self.update_pane_selection()
                    event.prevent_default()

    def update_pane_selection(self):
        """
        Update the selection based on the current pane
        """
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
        """
        Defines startup action.
        """
        self.push_screen(LoginModal(self))

    async def on_data_updated(self, message: DataUpdated) -> None:
        """
        Handler for DataUpdated callback; fetches and triggers render of event updates.
        """
        logging.debug(MOD_CODE + f"[*] Invoking data update in chat interface.")
        await self.update_groups(client.AppState["groups"])
        if hasattr(self, "current_group"):
            group_messages = self.get_messages_for_group(self.current_group)
            self.message_display.update(group_messages)
            scroll = self.query_one("#message-scroll", VerticalScroll)
            self.call_after_refresh(scroll.scroll_end, animate=False)

    async def update_groups(self, new_groups):
        """
        Re-renders updated group information.
        :param new_groups: Dictionary of new groups from client.
        """
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

    def get_messages_for_group(self, group_id):
        """
        Iterates through events to return all those in the specified group.
        
        :param group_id: Group ID to return events for.
        :return: Group chat history.
        :rtype: str
        """
        events = client.AppState["events"]
        groupchat = []
        logging.debug(MOD_CODE + f"[~] UI retrieved {len(events)} events from client.")
        for event in events:
            if event.groupID == group_id:
                if isinstance(event, protocol.MessageEvent):
                    groupchat.append(f"{event.senderUserID}: {event.message}")
        if (len(groupchat) == 0):
            return "No messages for this group."
        return "\n".join(groupchat)

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
