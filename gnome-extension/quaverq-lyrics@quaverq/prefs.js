import Gio from 'gi://Gio';
import Gtk from 'gi://Gtk';
import Adw from 'gi://Adw';

import {ExtensionPreferences, gettext as _}
    from 'resource:///org/gnome/Shell/Extensions/js/extensions/prefs.js';

export default class QuaverQLyricsPreferences extends ExtensionPreferences {
    async fillPreferencesWindow(window) {
        const settings = this.getSettings();
        window._settings = settings;

        const page = new Adw.PreferencesPage({
            title: _('Settings'),
            icon_name: 'preferences-system-symbolic',
        });

        page.add(this._buildModeGroup(settings));
        page.add(this._buildOsdGroup(settings));
        page.add(this._buildPanelGroup(settings));

        window.add(page);
    }

    _buildModeGroup(settings) {
        const group = new Adw.PreferencesGroup({
            title: _('Display Mode'),
        });

        const model = new Gtk.StringList({
            strings: [_('Both'), _('OSD Only'), _('Top Bar Only')],
        });
        const modeRow = new Adw.ComboRow({
            title: _('Display Mode'),
            subtitle: _('Where to show lyrics'),
            model,
        });

        const modeMap = ['both', 'osd', 'panel'];
        const current = settings.get_string('display-mode');
        modeRow.selected = Math.max(0, modeMap.indexOf(current));

        modeRow.connect('notify::selected', () => {
            settings.set_string('display-mode', modeMap[modeRow.selected]);
        });
        settings.connect('changed::display-mode', () => {
            const val = settings.get_string('display-mode');
            const idx = modeMap.indexOf(val);
            if (idx >= 0 && modeRow.selected !== idx)
                modeRow.selected = idx;
        });

        group.add(modeRow);
        return group;
    }

    _buildOsdGroup(settings) {
        const group = new Adw.PreferencesGroup({
            title: _('OSD Overlay'),
        });

        const fontRow = new Adw.SpinRow({
            title: _('Font Size'),
            subtitle: _('Main lyric line font size in pixels'),
            adjustment: new Gtk.Adjustment({
                lower: 12, upper: 48, step_increment: 1, value: settings.get_int('osd-font-size'),
            }),
        });
        settings.bind('osd-font-size', fontRow, 'value', Gio.SettingsBindFlags.DEFAULT);
        group.add(fontRow);

        const marginRow = new Adw.SpinRow({
            title: _('Bottom Margin'),
            subtitle: _('Distance from screen bottom in pixels'),
            adjustment: new Gtk.Adjustment({
                lower: 0, upper: 500, step_increment: 10, value: settings.get_int('osd-bottom-margin'),
            }),
        });
        settings.bind('osd-bottom-margin', marginRow, 'value', Gio.SettingsBindFlags.DEFAULT);
        group.add(marginRow);

        const opacityRow = new Adw.ActionRow({
            title: _('Background Opacity'),
        });
        const scale = new Gtk.Scale({
            orientation: Gtk.Orientation.HORIZONTAL,
            adjustment: new Gtk.Adjustment({
                lower: 0.0, upper: 1.0, step_increment: 0.05,
                value: settings.get_double('osd-opacity'),
            }),
            hexpand: true,
            draw_value: true,
            digits: 2,
            valign: Gtk.Align.CENTER,
        });
        settings.bind('osd-opacity', scale.adjustment, 'value', Gio.SettingsBindFlags.DEFAULT);
        opacityRow.add_suffix(scale);
        group.add(opacityRow);

        const translationRow = new Adw.SwitchRow({
            title: _('Show Translation'),
            subtitle: _('Display translation below the main lyric line'),
        });
        settings.bind('show-translation', translationRow, 'active', Gio.SettingsBindFlags.DEFAULT);
        group.add(translationRow);

        const nextRow = new Adw.SwitchRow({
            title: _('Show Next Line'),
            subtitle: _('Preview the next lyric line'),
        });
        settings.bind('show-next-line', nextRow, 'active', Gio.SettingsBindFlags.DEFAULT);
        group.add(nextRow);

        return group;
    }

    _buildPanelGroup(settings) {
        const group = new Adw.PreferencesGroup({
            title: _('Top Bar'),
        });

        const widthRow = new Adw.SpinRow({
            title: _('Max Width'),
            subtitle: _('Maximum width of the lyric label in pixels'),
            adjustment: new Gtk.Adjustment({
                lower: 100, upper: 800, step_increment: 50,
                value: settings.get_int('panel-max-width'),
            }),
        });
        settings.bind('panel-max-width', widthRow, 'value', Gio.SettingsBindFlags.DEFAULT);
        group.add(widthRow);

        const posModel = new Gtk.StringList({
            strings: [_('Center'), _('Left'), _('Right')],
        });
        const posRow = new Adw.ComboRow({
            title: _('Position'),
            subtitle: _('Where to place the indicator in the top bar'),
            model: posModel,
        });

        const posMap = ['center', 'left', 'right'];
        const currentPos = settings.get_string('panel-position');
        posRow.selected = Math.max(0, posMap.indexOf(currentPos));

        posRow.connect('notify::selected', () => {
            settings.set_string('panel-position', posMap[posRow.selected]);
        });
        settings.connect('changed::panel-position', () => {
            const val = settings.get_string('panel-position');
            const idx = posMap.indexOf(val);
            if (idx >= 0 && posRow.selected !== idx)
                posRow.selected = idx;
        });

        group.add(posRow);
        return group;
    }
}
