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

        page.add(this._buildPanelGroup(settings));

        window.add(page);
    }

    _buildPanelGroup(settings) {
        const group = new Adw.PreferencesGroup({
            title: _('Top Bar Lyrics'),
        });

        const widthRow = new Adw.SpinRow({
            title: _('Max Width'),
            subtitle: _('Maximum width of the lyric label in pixels'),
            adjustment: new Gtk.Adjustment({
                lower: 100, upper: 800, step_increment: 50,
                value: settings.get_int('panel-max-width'),
            }),
        });
        settings.bind('panel-max-width', widthRow, 'value',
            Gtk.SettingsBindFlags ? Gtk.SettingsBindFlags.DEFAULT : 0);
        group.add(widthRow);

        const posModel = new Gtk.StringList({
            strings: [_('Left of Clock'), _('Right of Clock')],
        });
        const posRow = new Adw.ComboRow({
            title: _('Position'),
            subtitle: _('Place lyrics left or right of the clock'),
            model: posModel,
        });

        const posMap = ['left', 'right'];
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
