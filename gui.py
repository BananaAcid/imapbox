#!/usr/bin/env python
# -*- coding:utf-8 -*-


# disable arg parsing for kivy
import os
os.environ['KIVY_NO_ARGS'] = '1'
#os.environ['KIVY_NO_CONSOLELOG'] = '1' -- will stop python as well
os.environ['KIVY_NO_FILELOG'] = '1'
os.environ['KIVY_LOG_MODE'] = 'PYTHON' # == do not interfere with logging

import sys
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.checkbox import CheckBox
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.core.window import Window

from dsn import account_to_dsn, create_account_name
from mailboxresource import get_folders


Window.size = (500, 430) #500,350
Window.clearcolor = (.17, .17, .17, 1) #(0.23, 0.38, 0.66, 1)
Window.resizable = False


color = {
    'label': (1, 1, 1, 1),
    'button': (0.53, 0.68, 1, 1),
    'output': (1, 1, 1, 0),
    'checkbox': (1, 1, 1, 1),
}


class MainWindow(BoxLayout):
    def __init__(self, options):
        super().__init__()
        self.orientation = 'vertical'
        self.padding = 30
        self.account = {}
        self.options = options

        self.add_widget(self.create_row('Host', '', placeholder_text='imap.server.tld', key='host', focus=True))
        self.add_widget(self.create_row('Port', '993', placeholder_text='993', key='port'))
        self.add_widget(self.create_row('Username', '', placeholder_text='your_username', key='username'))
        self.add_widget(self.create_row('Password', '', placeholder_text='your_password', key='password'))  # password=True, 
        self.add_widget(self.create_row('Remote folder\n(use __ALL__ to fetch all)', 'INBOX', placeholder_text='INBOX', key='remote_folder'))
        self.add_widget(self.create_row('Use SSL?', 'Y', typeCheckbox=True, key='ssl'))

        self.add_widget(self.create_row('Only show DSN (do not backup)', 'Y', typeCheckbox=True, key='show_DSN'))

        row = BoxLayout(orientation='horizontal', padding=[0, 20, 0, 0])
        button = Button(text="execute", color=color['label'], background_color=color['button'])
        button.bind(on_press=self.handle_button_clicked)
        row.add_widget(button)
        self.add_widget(row)

        row2 = BoxLayout(orientation='horizontal', padding=[0, 0, 0, 0])
        self.output = TextInput(text='', hint_text='<DSN>', foreground_color=color['label'], background_color=color['output'], multiline=True, readonly=True)
        self.write_tab = False
        self.output.bind(focus=self.on_text_input_focus)
        row2.add_widget(self.output)
        self.add_widget(row2)


    def create_row(self, label_text, text_input_text, password=False, typeCheckbox=False, placeholder_text=None, key=None, focus=False):
        row = BoxLayout(orientation='horizontal', padding=[0, 20, 0, 20])
        if typeCheckbox:
            checkbox = CheckBox(size_hint_x=0.5, color=color['checkbox'], active=True)
            # checkbox.bind(active=self.on_ssl_checkbox_active)
            if focus: checkbox.focus = True
            row.add_widget(Label(text=label_text, size_hint_x=0.5, color=color['label']))
            row.add_widget(checkbox)
            self.account[key or label_text.strip().lower()] = checkbox
        else:
            row.add_widget(Label(text=label_text, size_hint_x=0.5, color=color['label']))
            input = TextInput(text=text_input_text, multiline=False, password=password, hint_text=placeholder_text, size_hint_x=0.5)
            input.bind(focus=self.on_text_input_focus)
            input.write_tab = False
            if focus: input.focus = True
            row.add_widget(input)
            self.account[key or label_text.strip().lower()] = input
        return row

    # def on_ssl_checkbox_active(self, instance, value):
    #     # Hier können Sie Code ausführen, wenn die Checkbox aktiviert oder deaktiviert wird
    #     print("SSL-Checkbox aktiviert:", value)
        
    
    def handle_button_clicked(self, event):
        account = {}
        for key, value in self.account.items():
            if isinstance(value, TextInput):
                account[key] = value.text
            elif isinstance(value, CheckBox):
                account[key] = value.active

        #     if key != 'password':
        #         print(f"{key}: {value.text}")
        # print(f"password: {'*' * len(self.account['password'].text)}")
        
        dsn = account_to_dsn(account)

        self.output.text = dsn
        account['name'] = create_account_name(account)
        self.options['accounts'] = [account]

        self.output.text = 'Testing connection' + '\n' + dsn
        try:
            get_folders(account)
            self.output.text = 'Connection successful' + '\n' + dsn
        except:
            self.output.text = 'FAILED: Login and folder retrival' + '\n' + dsn
            return

        if not account['show_DSN']:
            Window.close()


    def on_text_input_focus(self, instance, value):
        if value:
            # got focus
            if instance.text == instance.hint_text:
                # has placeholder
                instance.text = ""
        else:
            # lot focus
            if instance.text == "":
                # input is empty
                instance.text = instance.hint_text


class MyApp(App):
    def build(self):
        self.title = "IMAPBOX"
        return MainWindow(self.options)


def open_gui(options):
    app = MyApp()
    app.options = options
    app.run()

    if not options['accounts'] or options['accounts'][0]['show_DSN']:
        sys.exit(0)
