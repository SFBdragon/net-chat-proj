# ---------------------------------------------------------------------------------------

# Textual for TUI
# Logging
import logging
import os
from pathlib import Path

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.events import Key
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    DirectoryTree,
    Input,
    Label,
    ListItem,
    ListView,
    Static,
)

logging.basicConfig(
    level=logging.DEBUG,
    filename="debug.log",
    format="%(asctime)s %(message)s ",
    datefmt="%H:%M:%S %d/%m/%Y",
)
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
        # password = self.query_one("#login-password", Input).value

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
    "action-add-users": ("Add Users", "Group Description", "Users"),
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

            case "Add Users":
                logging.debug(MOD_CODE + "[*] Adding users group.")
                group_description = self.query_one("#input-1", Input).value
                group_members = (self.query_one("#input-2", Input).value).split(",")
                for member in group_members:
                    await client.add_group_member(client.AppState["current_group"], member)

        self.dismiss()

    def on_key(self, event: Key) -> None:
        """
        Handles keypresses; escape to dismiss.
        """
        if event.key == "escape":
            event.stop()
            self.dismiss()
        # Prevent propagation.
        if event.key not in ("tab", "backspace", "enter"):
            event.stop()
            event.prevent_default()


# ---------------------------------------------------------------------------------------

# File picker modal


class PlainDirectoryTree(DirectoryTree):
    """
    DirectoryTree with icons stripped so they don't render as broken characters.
    """

    ICON_NODE = ""
    ICON_NODE_EXPANDED = ""
    ICON_FILE = ""


class FilePickerModal(ModalScreen):
    """
    Modal for picking files with directory tree and auto navigation.
    """

    CSS_PATH = str(Path(__file__).parent / "../styles/action_modal.tcss")

    def compose(self) -> ComposeResult:
        """
        Specifies modal format.
        """
        with Vertical(id="modal-box"):
            yield Label("Send File", id="modal-title")
            yield Input(
                placeholder="File path...", id="file-path-input", classes="modal-input"
            )
            yield PlainDirectoryTree(str(Path("~/").expanduser()), id="file-tree")
            yield Input(
                placeholder="Description", id="file-description", classes="modal-input"
            )
            yield Button("Submit", id="modal-submit")

    def on_screen_resume(self) -> None:
        self.query_one(PlainDirectoryTree).focus()

    def on_mount(self) -> None:
        self.query_one(PlainDirectoryTree).focus()

    def on_directory_tree_file_selected(
        self, event: DirectoryTree.FileSelected
    ) -> None:
        """
        Sets input bar when file from tree is selected.
        """
        event.stop()
        # Set flag to prevent on_input_changed from re-syncing the tree
        self._syncing_from_tree = True
        self.query_one("#file-path-input", Input).value = str(event.path)
        self._syncing_from_tree = False

    def on_input_changed(self, event: Input.Changed) -> None:
        """
        Updates tree when input bar changes.
        """
        if event.input.id != "file-path-input":
            return
        # Skip if this change was triggered by a tree selection
        if getattr(self, "_syncing_from_tree", False):
            return
        p = Path(event.value).expanduser()
        tree = self.query_one(PlainDirectoryTree)
        # Navigate to the closest valid parent so partial paths don't crash
        if p.is_dir():
            tree.path = p
        elif p.parent.is_dir():
            tree.path = p.parent

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """
        Shares file on submit.
        """
        event.stop()
        file_path = self.query_one("#file-path-input", Input).value
        description = self.query_one("#file-description", Input).value
        logging.debug(MOD_CODE + f"[*] Sharing file {file_path}: {description}")
        self.dismiss((file_path, description))
        await client.share_file(file_path)

    def on_key(self, event: Key) -> None:
        if event.key == "escape":
            event.stop()
            self.dismiss(None)
        if event.key not in ("tab", "backspace", "enter"):
            event.stop()
            event.prevent_default()


# ---------------------------------------------------------------------------------------

# File message widget


class FileMessageItem(ListItem):
    """
    A clickable list item representing a shared file event.
    Stores the originating FileAvailableEvent so it can be downloaded on selection.
    """

    DEFAULT_CSS = """
    FileMessageItem {
        background: $panel;
        color: $accent;
        padding: 0 1;
    }
    FileMessageItem:hover {
        background: $accent 20%;
    }
    FileMessageItem.--highlight {
        background: $accent 30%;
    }
    """

    def __init__(self, file_event: protocol.FileAvailableEvent) -> None:
        self.file_event = file_event
        label = f"[bold]{file_event.senderUserID}[/bold] shared [italic]{file_event.fileName}[/italic] [dim][enter to download][/dim]"
        super().__init__(Label(label))


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
                yield Static("Join/create a group.")

            with Vertical(id="right-pane"):
                yield Static("", id="group-banner")
                # ListView replaces the single Static — each message is its own item
                yield ListView(id="message-list")
                yield self.message_input

            with Vertical(id="action-pane"):
                yield Button("Share File", id="action-send-file", classes="action-btn")
                yield Button(
                    "Create Group", id="action-create-group", classes="action-btn"
                )
                yield Button("Add Users", id="action-add-users", classes="action-btn")

        self.current_pane = "left"
        self.selected_button = 0
        self.selected_action = 0
        self.action_ids = [
            "action-send-file",
            "action-create-group",
            "action-add-users",
        ]

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """
        Handles button presses in chat interface.
        """
        btn_id = event.button.id

        # Infer action from button ID
        if btn_id in ACTION_CONFIG:
            if btn_id == "action-send-file":
                self.app.push_screen(FilePickerModal())
            else:
                title, field1, field2 = ACTION_CONFIG[btn_id]
                self.app.push_screen(ActionModal(title, field1, field2))

        else:
            group_id = int(btn_id.split("-")[1])
            self.current_group = group_id

            client.AppState["current_group"] = group_id

            group_banner = f"[bold]{event.button.label}[/bold]\n{' '.join(list(dict.fromkeys(event.button.group_members)))}"
            
            self.current_banner = group_banner
            self.query_one("#group-banner", Static).update(f"{group_banner}")

            group_buttons = [
                b for b in self.query(Button) if b.id and b.id.startswith("group-")
            ]
            for idx, button in enumerate(group_buttons):
                button.remove_class("selected")
                if button.id == btn_id:
                    button.add_class("selected")
                    button.focus()
                    self.current_pane = "left"

            self.render_messages_for_group(group_id)

            lv = self.query_one("#message-list", ListView)
            self.call_after_refresh(lv.scroll_end, animate=False)

    async def on_list_view_selected(self, event: ListView.Selected) -> None:
        """
        Handles selection of a message list item.
        If the selected item is a FileMessageItem, trigger a file download.
        """
        if isinstance(event.item, FileMessageItem):
            file_event = event.item.file_event
            logging.debug(
                MOD_CODE
                + f"[*] Downloading file {file_event.fileName} from {file_event.senderUserID}"
            )
            os.makedirs("./chat-downloads", exist_ok=True)
            try:
                success = await client.get_file(
                    file_event.senderUserID,
                    file_event.sha256,
                    f"./chat-downloads/{file_event.fileName}",
                )
                if success:
                    self.notify(f"{file_event.fileName} downloaded successfully.", severity="information")
                else:
                    self.notify(f"{file_event.fileName} downloaded failed.", severity="information")
            except:
                self.notify(f"{file_event.fileName} downloaded failed.", severity="information")

    def on_screen_suspend(self) -> None:
        """
        Called when a modal is pushed on top — disable key handling.
        """
        self._saved_pane = self.current_pane
        self.current_pane = None

    def on_screen_resume(self) -> None:
        """Called when modal is dismissed — restore key handling."""
        if hasattr(self, "_saved_pane") and self._saved_pane is not None:
            self.current_pane = self._saved_pane
            self.update_pane_selection()

    async def on_key(self, event: Key) -> None:
        """
        Handle key press events for navigation.
        """
        logging.debug(
            MOD_CODE
            + f"[~] Active screen: {self.app.screen}, focused: {self.app.focused}"
        )
        match self.current_pane:
            case "left":
                if event.key == "right":
                    self.current_pane = "right"
                    self.update_pane_selection()

                elif event.key == "down":
                    self.selected_button = min(
                        self.selected_button + 1, len(self.groups) - 1
                    )
                    self.update_pane_selection()

                elif event.key == "up":
                    self.selected_button = max(self.selected_button - 1, 0)
                    self.update_pane_selection()

            case "right":
                if event.key == "down":
                    self.query_one("#message-list", ListView).scroll_down()
                    event.prevent_default()

                elif event.key == "up":
                    self.query_one("#message-list", ListView).scroll_up()
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
                    self.selected_action = min(
                        self.selected_action + 1, len(self.action_ids) - 1
                    )
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
            self.render_messages_for_group(self.current_group)
            lv = self.query_one("#message-list", ListView)
            self.call_after_refresh(lv.scroll_end, animate=False)

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
                button = Button(group_name, id=f"group-{group_id}")
                button.group_members = group_data["members"]
                left_pane.mount(button)
        else:
            left_pane.mount(Static("Join/create a group."))

    def render_messages_for_group(self, group_id):
        """
        Clears and repopulates the message ListView for the given group.
        Regular messages become plain ListItems; file events become
        FileMessageItems which trigger a download when selected.

        :param group_id: Group ID whose messages should be rendered.
        """
        events = client.AppState["events"]
        lv = self.query_one("#message-list", ListView)
        lv.clear()

        logging.debug(MOD_CODE + f"[~] UI retrieved {len(events)} events from client.")
        
        #group_name = group_id;
        #group_members = client.AppState["groups"][group_id]["members"];
        #group_banner = f"[bold]{group_name}[/bold]\n{' '.join(group_members)}"
        #self.query_one("#group-banner", Static).update(f"{group_banner}")
        self.query_one("#group-banner", Static).update("")
        self.current_banner = f"[bold]{group_id}[/bold]\n"

        found = False
        processed_events = []
        for event in events:
            if event.groupID != group_id:
                continue
            logging.debug(MOD_CODE + f" [E] EventID is {event.eventID}")
            if event.eventID not in processed_events:
                found = True
                if isinstance(event, protocol.MessageEvent):
                    lv.append(ListItem(Label(f"{event.senderUserID}: {event.message}")))
                elif isinstance(event, protocol.FileAvailableEvent):
                    lv.append(FileMessageItem(event))
                elif isinstance(event, protocol.AddMemberEvent):
                    logging.debug(MOD_CODE + f" [=] This event is a AddMemberEvent: {event}")
                    self.query_one("#group-banner", Static).update("")
                    self.current_banner = f"{self.current_banner}{event.userID} "
                    self.query_one("#group-banner", Static).update(f"{self.current_banner}")
                    event.userID
                processed_events.append(event.eventID)

        if not found:
            lv.append(ListItem(Label("No messages for this group.")))


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
