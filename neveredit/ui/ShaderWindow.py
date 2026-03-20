"""Shader selection and tuning window for neveredit."""
import logging

import wx

logger = logging.getLogger("neveredit")


class ShaderWindow(wx.Frame):
    """Window for shader availability, selection, and parameter tuning."""

    def __init__(self, parent=None):
        wx.Frame.__init__(
            self,
            parent,
            -1,
            "Shaders",
            style=wx.DEFAULT_FRAME_STYLE | wx.FRAME_FLOAT_ON_PARENT,
        )

        self.shader_manager = None
        self.on_shader_changed = None
        self._shader_keys = []
        self._parameter_controls = {}

        panel = wx.Panel(self, -1)
        sizer = wx.BoxSizer(wx.VERTICAL)

        self.active_shader_label = wx.StaticText(panel, -1, "Active shader: No Shader")
        sizer.Add(self.active_shader_label, 0, wx.ALL | wx.EXPAND, 5)

        list_label = wx.StaticText(panel, -1, "Enabled shaders:")
        sizer.Add(list_label, 0, wx.LEFT | wx.RIGHT | wx.TOP, 5)

        self.shader_list = wx.CheckListBox(panel, -1, size=(320, 150))
        self.shader_list.Bind(wx.EVT_LISTBOX, self.OnShaderSelected)
        self.shader_list.Bind(wx.EVT_CHECKLISTBOX, self.OnShaderAvailabilityChanged)
        sizer.Add(self.shader_list, 0, wx.ALL | wx.EXPAND, 5)

        desc_label = wx.StaticText(panel, -1, "Description:")
        sizer.Add(desc_label, 0, wx.LEFT | wx.RIGHT | wx.TOP, 5)

        self.description = wx.TextCtrl(
            panel,
            -1,
            "",
            style=wx.TE_MULTILINE | wx.TE_READONLY,
            size=(320, 80),
        )
        sizer.Add(self.description, 0, wx.ALL | wx.EXPAND, 5)

        params_box = wx.StaticBoxSizer(wx.StaticBox(panel, -1, "Parameters"), wx.VERTICAL)
        self.parameter_panel = wx.Panel(panel, -1)
        self.parameter_sizer = wx.FlexGridSizer(0, 2, 6, 8)
        self.parameter_sizer.AddGrowableCol(1, 1)
        self.parameter_panel.SetSizer(self.parameter_sizer)
        params_box.Add(self.parameter_panel, 1, wx.ALL | wx.EXPAND, 5)
        sizer.Add(params_box, 1, wx.ALL | wx.EXPAND, 5)

        button_row = wx.BoxSizer(wx.HORIZONTAL)
        self.reset_button = wx.Button(panel, wx.ID_ANY, "Reset Shader")
        self.reset_button.Bind(wx.EVT_BUTTON, self.OnResetShader)
        button_row.Add(self.reset_button, 0, wx.RIGHT, 8)

        apply_btn = wx.Button(panel, wx.ID_APPLY, "Apply Shader")
        apply_btn.Bind(wx.EVT_BUTTON, self.OnApplyShader)
        button_row.Add(apply_btn, 0)
        sizer.Add(button_row, 0, wx.ALL | wx.ALIGN_CENTER_HORIZONTAL, 5)

        panel.SetSizer(sizer)

        self.SetClientSize((360, 560))
        self.SetMinSize((340, 520))

    def _selected_shader_key(self):
        selection = self.shader_list.GetSelection()
        if selection == wx.NOT_FOUND or selection >= len(self._shader_keys):
            return None
        return self._shader_keys[selection]

    def _emit_shader_changed(self, shader_key):
        if not self.on_shader_changed:
            return
        try:
            self.on_shader_changed(shader_key)
        except TypeError:
            self.on_shader_changed()

    def _refresh_active_label(self):
        if not self.shader_manager:
            self.active_shader_label.SetLabel("Active shader: No Shader")
            return
        shader_key = self.shader_manager.get_current_shader()
        shader_name = self.shader_manager.shaders[shader_key].name
        self.active_shader_label.SetLabel("Active shader: %s" % shader_name)

    def _clear_parameter_controls(self):
        self.parameter_panel.DestroyChildren()
        self.parameter_sizer = wx.FlexGridSizer(0, 2, 6, 8)
        self.parameter_sizer.AddGrowableCol(1, 1)
        self.parameter_panel.SetSizer(self.parameter_sizer)
        self._parameter_controls = {}

    def _create_color_control(self, parent, value):
        rgb = [int(max(0.0, min(1.0, component)) * 255.0) for component in value]
        colour = wx.Colour(rgb[0], rgb[1], rgb[2])
        control = wx.ColourPickerCtrl(parent, -1, colour=colour)
        control.Bind(wx.EVT_COLOURPICKER_CHANGED, self.OnParameterChanged)
        return control

    def _create_numeric_control(self, parent, parameter):
        value_type = parameter.get('type')
        value = parameter.get('value')
        minimum = parameter.get('min', 0)
        maximum = parameter.get('max', 100)
        if value_type == 'int':
            control = wx.SpinCtrl(parent, -1, min=int(minimum), max=int(maximum), initial=int(value))
            control.Bind(wx.EVT_SPINCTRL, self.OnParameterChanged)
            control.Bind(wx.EVT_TEXT, self.OnParameterChanged)
            return control
        control = wx.SpinCtrlDouble(parent, -1)
        control.SetDigits(2)
        control.SetIncrement(float(parameter.get('step', 0.1)))
        control.SetRange(float(minimum), float(maximum))
        control.SetValue(float(value))
        control.Bind(wx.EVT_SPINCTRLDOUBLE, self.OnParameterChanged)
        control.Bind(wx.EVT_TEXT, self.OnParameterChanged)
        return control

    def _rebuild_parameter_controls(self, shader_key):
        self._clear_parameter_controls()
        if not self.shader_manager or not shader_key:
            self.parameter_panel.Layout()
            return

        parameters = self.shader_manager.get_shader_parameters(shader_key)
        if not parameters:
            self.parameter_sizer.Add(
                wx.StaticText(self.parameter_panel, -1, "This shader has no adjustable parameters."),
                0,
                wx.ALL,
                2,
            )
            self.parameter_sizer.Add((0, 0))
            self.parameter_panel.Layout()
            self.Layout()
            return

        for parameter in parameters:
            label = wx.StaticText(self.parameter_panel, -1, parameter.get('label', parameter['key']))
            self.parameter_sizer.Add(label, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 2)
            if parameter.get('type') == 'color':
                control = self._create_color_control(self.parameter_panel, parameter.get('value'))
            else:
                control = self._create_numeric_control(self.parameter_panel, parameter)
            self._parameter_controls[control.GetId()] = parameter
            self.parameter_sizer.Add(control, 1, wx.EXPAND | wx.ALL, 2)

        self.parameter_panel.Layout()
        self.Layout()

    def _refresh_shader_ui(self):
        self.shader_list.Clear()
        self._shader_keys = []
        self.description.SetValue("")
        self._clear_parameter_controls()

        if not self.shader_manager:
            self._refresh_active_label()
            self.Layout()
            return

        enabled_shaders = set(self.shader_manager.get_enabled_shaders())
        for shader_key, shader_name in self.shader_manager.get_all_shader_list():
            self.shader_list.Append(shader_name)
            self._shader_keys.append(shader_key)
            self.shader_list.Check(len(self._shader_keys) - 1, shader_key in enabled_shaders)

        current_shader = self.shader_manager.get_current_shader()
        if current_shader in self._shader_keys:
            self.shader_list.SetSelection(self._shader_keys.index(current_shader))
        elif self._shader_keys:
            self.shader_list.SetSelection(0)

        self._refresh_active_label()
        self.OnShaderSelected(None)

    def set_shader_manager(self, shader_manager):
        self.shader_manager = shader_manager
        self._refresh_shader_ui()

    def set_on_shader_changed_callback(self, callback):
        self.on_shader_changed = callback

    def OnShaderSelected(self, event):
        shader_key = self._selected_shader_key()
        if not shader_key or not self.shader_manager:
            self.description.SetValue("")
            self._rebuild_parameter_controls(None)
            return
        self.description.SetValue(self.shader_manager.get_shader_description(shader_key))
        self._rebuild_parameter_controls(shader_key)

    def OnShaderAvailabilityChanged(self, event):
        if not self.shader_manager:
            return
        index = event.GetSelection()
        if index == wx.NOT_FOUND or index >= len(self._shader_keys):
            return
        shader_key = self._shader_keys[index]
        if shader_key == 'None' and not self.shader_list.IsChecked(index):
            self.shader_list.Check(index, True)
            return

        enabled = [
            key for idx, key in enumerate(self._shader_keys)
            if key != 'None' and self.shader_list.IsChecked(idx)
        ]
        previous_shader = self.shader_manager.get_current_shader()
        self.shader_manager.set_enabled_shaders(enabled)
        self._refresh_active_label()
        if self.shader_manager.get_current_shader() != previous_shader:
            self._emit_shader_changed(self.shader_manager.get_current_shader())

    def _get_control_value(self, control, parameter):
        if parameter.get('type') == 'color':
            colour = control.GetColour()
            return [colour.Red() / 255.0, colour.Green() / 255.0, colour.Blue() / 255.0]
        if parameter.get('type') == 'int':
            return int(control.GetValue())
        return float(control.GetValue())

    def OnParameterChanged(self, event):
        shader_key = self._selected_shader_key()
        if not self.shader_manager or not shader_key:
            return
        parameter = self._parameter_controls.get(event.GetEventObject().GetId())
        if not parameter:
            return
        value = self._get_control_value(event.GetEventObject(), parameter)
        self.shader_manager.set_parameter_value(shader_key, parameter['key'], value)
        if shader_key == self.shader_manager.get_current_shader():
            self._emit_shader_changed(shader_key)

    def OnApplyShader(self, event):
        shader_key = self._selected_shader_key()
        if not shader_key or not self.shader_manager:
            return
        self.shader_manager.set_current_shader(shader_key)
        if shader_key in self._shader_keys:
            self.shader_list.Check(self._shader_keys.index(shader_key), True)
        self._refresh_active_label()
        self._emit_shader_changed(shader_key)
        logger.info("Applied shader: %s", self.shader_manager.shaders[shader_key].name)

    def OnResetShader(self, event):
        shader_key = self._selected_shader_key()
        if not shader_key or not self.shader_manager:
            return
        self.shader_manager.reset_shader_parameters(shader_key)
        self._rebuild_parameter_controls(shader_key)
        if shader_key == self.shader_manager.get_current_shader():
            self._emit_shader_changed(shader_key)