# UI Visibility
def set_layout_visible(layout, visible) -> None:
    for i in range(layout.count()):
        item = layout.itemAt(i)

        if item.widget():
            if visible:
                item.widget().show()
            else:
                item.widget().hide()
        elif item.layout():
            set_layout_visible(item.layout(), visible)