class Client:

    {
        "testID" = 123,
        current_group_id = '',
        last_event_id = 0
    }
    

    def __init__(self, ui_refresh):
        self.on_state_update = ui_refresh
        self.send_update()

    def send_update(self):
        self.on_state_update("data1")
        print("Hello!")

# set_focused_group
    def get_testID(self):
        return AppState.anotherID

    def set_current_group(self, group_id):
        curretn_group_id = groupd_id

