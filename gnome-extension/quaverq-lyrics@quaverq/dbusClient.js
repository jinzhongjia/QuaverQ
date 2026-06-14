import Gio from 'gi://Gio';

const BUS_NAME = 'org.quaverq.Lyrics1';
const OBJECT_PATH = '/org/quaverq/Lyrics';

const LYRICS_IFACE_XML = `<node>
  <interface name="org.quaverq.Lyrics1">
    <method name="GetLyric">
      <arg type="s" direction="out" name="mid"/>
      <arg type="b" direction="out" name="has_word_timing"/>
      <arg type="a(xssa(xxs))" direction="out" name="lines"/>
    </method>
    <method name="GetWindow">
      <arg type="i" direction="in" name="before"/>
      <arg type="i" direction="in" name="after"/>
      <arg type="a(xss)" direction="out" name="window"/>
      <arg type="i" direction="out" name="active_in_window"/>
    </method>
    <property name="Mid" type="s" access="read"/>
    <property name="TrackId" type="o" access="read"/>
    <property name="PositionMs" type="x" access="read"/>
    <property name="ActiveLine" type="i" access="read"/>
    <property name="ActiveWord" type="i" access="read"/>
    <property name="HasWordTiming" type="b" access="read"/>
    <property name="HasTranslation" type="b" access="read"/>
    <property name="LineCount" type="i" access="read"/>
    <signal name="LyricChanged">
      <arg name="mid" type="s"/>
    </signal>
    <signal name="LineEntered">
      <arg name="line" type="i"/>
      <arg name="ts_ms" type="x"/>
    </signal>
  </interface>
</node>`;

const LyricsProxy = Gio.DBusProxy.makeProxyWrapper(LYRICS_IFACE_XML);

export class LyricsDBusClient {
    constructor({onLyricLoaded, onActiveChanged, onDisconnected}) {
        this._onLyricLoaded = onLyricLoaded;
        this._onActiveChanged = onActiveChanged;
        this._onDisconnected = onDisconnected;

        this._proxy = null;
        this._watchId = 0;
        this._lyricSignalId = 0;

        this._lines = [];
        this._hasWordTiming = false;
        this._hasTranslation = false;
        this._mid = '';
    }

    get lines() {
        return this._lines;
    }

    get hasWordTiming() {
        return this._hasWordTiming;
    }

    get hasTranslation() {
        return this._hasTranslation;
    }

    get mid() {
        return this._mid;
    }

    get connected() {
        return this._proxy !== null && this._proxy.g_name_owner !== null;
    }

    start() {
        this._watchId = Gio.bus_watch_name(
            Gio.BusType.SESSION,
            BUS_NAME,
            Gio.BusNameWatcherFlags.NONE,
            (_conn, _name, _owner) => this._onAppeared(),
            (_conn, _name) => this._onVanished(),
        );
    }

    getWindowAsync(before, after) {
        if (!this._proxy)
            return Promise.resolve(null);

        return new Promise((resolve) => {
            this._proxy.GetWindowRemote(before, after, ([window, activeInWindow], error) => {
                if (error) {
                    resolve(null);
                    return;
                }
                resolve({window, activeInWindow});
            });
        });
    }

    destroy() {
        if (this._watchId) {
            Gio.bus_unwatch_name(this._watchId);
            this._watchId = 0;
        }
        this._cleanupProxy();
        this._lines = [];
        this._mid = '';
    }

    _onAppeared() {
        LyricsProxy(
            Gio.DBus.session,
            BUS_NAME,
            OBJECT_PATH,
            (proxy, error) => {
                if (error) {
                    console.error(`[QuaverQ Lyrics] proxy creation failed: ${error}`);
                    return;
                }
                this._setupProxy(proxy);
            },
            null,
            Gio.DBusProxyFlags.NONE,
        );
    }

    _onVanished() {
        this._cleanupProxy();
        this._lines = [];
        this._hasWordTiming = false;
        this._hasTranslation = false;
        this._mid = '';
        this._onDisconnected();
    }

    _setupProxy(proxy) {
        this._proxy = proxy;

        proxy.connectObject(
            'g-properties-changed', (_p, changed, _invalidated) => {
                this._onPropertiesChanged(changed);
            },
            this,
        );

        this._lyricSignalId = proxy.connectSignal(
            'LyricChanged',
            (_proxy, _sender, [mid]) => {
                this._reloadLyric(mid);
            },
        );

        this._reloadLyric(null);
    }

    _cleanupProxy() {
        if (!this._proxy)
            return;

        if (this._lyricSignalId) {
            this._proxy.disconnectSignal(this._lyricSignalId);
            this._lyricSignalId = 0;
        }
        this._proxy.disconnectObject(this);
        this._proxy = null;
    }

    _reloadLyric(_mid) {
        if (!this._proxy)
            return;

        this._proxy.GetLyricRemote(([mid, hasWordTiming, lines], error) => {
            if (error) {
                console.error(`[QuaverQ Lyrics] GetLyric failed: ${error}`);
                return;
            }
            this._mid = mid;
            this._hasWordTiming = hasWordTiming;
            this._lines = lines;
            this._hasTranslation = this._proxy.HasTranslation;
            this._onLyricLoaded(mid, lines, hasWordTiming, this._hasTranslation);
        });
    }

    _onPropertiesChanged(changed) {
        const props = changed.deepUnpack();

        let activeChanged = false;
        if ('ActiveLine' in props || 'ActiveWord' in props)
            activeChanged = true;

        if ('HasTranslation' in props)
            this._hasTranslation = props['HasTranslation'].deepUnpack();

        if (activeChanged) {
            const line = this._proxy.ActiveLine;
            const word = this._proxy.ActiveWord;
            this._onActiveChanged(line, word);
        }
    }
}
