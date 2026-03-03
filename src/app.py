# ---------------------------------------------------------------------------------------

# Textual for TUI
from textual.app import App, ComposeResult
from textual.containers import Horizontal, VerticalScroll, Vertical, Center
from textual.screen import ModalScreen
from textual.widgets import Static, Button, Input, Label
from textual.events import Key

# ---------------------------------------------------------------------------------------

# Sample data
groups = [
    (1, "Group 1"),
    (2, "Group 2"),
    (3, "Group 3"),
    (4, "Group 4"),
]

messages = [
    (1, 101, "Hello from user 101 in Group 1"),
    (1, 102, "Hello from user 102 in Group 1"),
    (2, 101, "Message from user 101 in Group 2"),
    (3, 103, "User 103 says hi in Group 3"),
    (3, 104, "User 104 has a message in Group 3"),
]

# ---------------------------------------------------------------------------------------

def get_messages_for_group(group_id):
    return [
        f"[{from_user}] {content}\n" * 100
        for g_id, from_user, content in messages
        if g_id == group_id
    ]


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
            yield Input(placeholder=self._field1,  id="input-1", classes="modal-input")
            yield Input(placeholder=self._field2, id="input-2", classes="modal-input")
            yield Button("Submit", id="modal-submit")

    def on_button_pressed(self, event: Button.Pressed) -> None:
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
        width: 5;
        border: round #A9B665;
        layout: vertical;
        align: center bottom;
        padding: 0 0 1 0;
    }

    .action-btn {
        width: 3;
        height: 2;
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
        with Horizontal():
            with VerticalScroll(id="left-pane"):
                for group_id, group_name in groups:
                    yield Button(group_name, id=f"group-{group_id}")

            with Vertical(id="right-pane"):
                yield Static("", id="group-banner")
                with VerticalScroll(id="message-scroll"):
                    self.message_display = Static("Select a group to see messages.")
                    yield self.message_display
                yield Input(placeholder="Type a message...", id="message-input")

            with Vertical(id="action-pane"):
                yield Button("F", id="action-send-file", classes="action-btn")
                yield Button("G", id="action-create-group", classes="action-btn")
                yield Button("E", id="action-edit-group", classes="action-btn")

        self.current_pane = "left"
        self.selected_button = 0
        self.selected_action = 0
        self.action_ids = ["action-send-file", "action-create-group", "action-edit-group"]

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id

        # TODO fix modal inputs
        if btn_id in ACTION_CONFIG:
            title, field1, field2 = ACTION_CONFIG[btn_id]
            self.app.push_screen(ActionModal(title, field1, field2))
            return

        group_id = int(btn_id.split("-")[1])
        group_name = next(name for gid, name in groups if gid == group_id)

        self.query_one("#group-banner", Static).update(f" {group_name}")

        group_messages = get_messages_for_group(group_id)
        if group_messages:
            self.message_display.update("\n".join(group_messages))
        else:
            self.message_display.update("No messages for this group.")

        scroll = self.query_one("#message-scroll", VerticalScroll)
        self.call_after_refresh(scroll.scroll_end, animate=False)

    # Handle key press events for navigation
    def on_key(self, event: Key) -> None:
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
            self.selected_action = min(self.selected_action + 1, len(self.action_ids) - 1)
            self.update_pane_selection()
            event.prevent_default()

        elif event.key == "up" and self.current_pane == "action":
            self.selected_action = max(self.selected_action - 1, 0)
            self.update_pane_selection()
            event.prevent_default()

        elif event.key == "down" and self.current_pane == "left":
            self.selected_button = min(self.selected_button + 1, len(groups) - 1)
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
            group_buttons = [b for b in self.query(Button) if b.id and b.id.startswith("group-")]
            for idx, button in enumerate(group_buttons):
                button.remove_class("selected")
                if idx == self.selected_button:
                    button.add_class("selected")
                    button.focus()
        elif self.current_pane == "right":
            self.query_one("#message-input", Input).focus()
        elif self.current_pane == "action":
            action_buttons = [b for b in self.query(Button) if b.id and b.id.startswith("action-")]
            for idx, button in enumerate(action_buttons):
                button.remove_class("selected")
                if idx == self.selected_action:
                    button.add_class("selected")
                    button.focus()

    def on_mount(self) -> None:
        self.update_pane_selection()


if __name__ == "__main__":
    ChatInterface().run()
