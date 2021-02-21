"""The Teufel Raumfeld integration."""
import asyncio
import inspect
import logging
import os
import urllib.parse

import hassfeld
from hassfeld.constants import (
    TRIGGER_UPDATE_DEVICES,
    TRIGGER_UPDATE_HOST_INFO,
    TRIGGER_UPDATE_SYSTEM_STATE,
    TRIGGER_UPDATE_ZONE_CONFIG,
)
import voluptuous as vol
import xmltodict

from homeassistant.components.media_player import BrowseMedia
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    ATTR_EVENT_WSUPD_TYPE,
    DIDL_ATTR_CHILD_CNT,
    DIDL_ATTR_ID,
    DIDL_ELEM_ALBUM,
    DIDL_ELEM_ART_URI,
    DIDL_ELEM_ARTIST,
    DIDL_ELEM_CLASS,
    DIDL_ELEM_CONTAINER,
    DIDL_ELEM_ITEM,
    DIDL_ELEM_TITLE,
    DIDL_ELEMENT,
    DIDL_VALUE,
    DOMAIN,
    EVENT_WEBSERVICE_UPDATE,
    MEDIA_CONTENT_ID_SEP,
    MESSAGE_PHASE_ALPHA,
    PLATFORMS,
    POSINF_ELEM_ABS_TIME,
    POSINF_ELEM_DURATION,
    POSINF_ELEM_TRACK,
    POSINF_ELEM_TRACK_DATA,
    POSINF_ELEM_URI,
    SERVICE_GROUP,
    SUPPORTED_OBJECT_IDS,
    SUPPORTED_OBJECT_PREFIXES,
    TRACKINF_ALBUM,
    TRACKINF_ARTIST,
    TRACKINF_IMGURI,
    TRACKINF_TITLE,
    UNSUPPORTED_OBJECT_IDS,
    UPNP_CLASS_ALBUM,
    UPNP_CLASS_AUDIO_ITEM,
    UPNP_CLASS_LINE_IN,
    UPNP_CLASS_PLAYLIST_CONTAINER,
    UPNP_CLASS_PODCAST_EPISODE,
    UPNP_CLASS_RADIO,
    UPNP_CLASS_TRACK,
    URN_CONTENT_DIRECTORY,
)

_LOGGER = logging.getLogger(__name__)


def log_debug(message):
    name = inspect.currentframe().f_back.f_code.co_name
    filename = inspect.currentframe().f_back.f_code.co_filename
    basename = os.path.basename(filename)
    _LOGGER.debug("%s->%s: %s", basename, name, message)


def log_info(message):
    _LOGGER.debug(message)


def log_warn(message):
    _LOGGER.warn(message)


def log_error(message):
    _LOGGER.error(message)


def log_fatal(message):
    name = inspect.currentframe().f_back.f_code.co_name
    filename = inspect.currentframe().f_back.f_code.co_filename
    basename = os.path.basename(filename)
    _LOGGER.fatal("%s->%s: %s", basename, name, message)


async def async_setup(hass: HomeAssistant, config: dict):
    """Set up the Teufel Raumfeld component."""
    log_warn(MESSAGE_PHASE_ALPHA)
    hass.data[DOMAIN] = {}
    return True


def event_on_update(hass, update_type):
    log_info("Update event triggered for type: %s" % update_type)
    if update_type == TRIGGER_UPDATE_HOST_INFO:
        hass.bus.fire(
            EVENT_WEBSERVICE_UPDATE, {ATTR_EVENT_WSUPD_TYPE: TRIGGER_UPDATE_HOST_INFO}
        )
    elif update_type == TRIGGER_UPDATE_ZONE_CONFIG:
        hass.bus.fire(
            EVENT_WEBSERVICE_UPDATE, {ATTR_EVENT_WSUPD_TYPE: TRIGGER_UPDATE_ZONE_CONFIG}
        )
    elif update_type == TRIGGER_UPDATE_DEVICES:
        hass.bus.fire(
            EVENT_WEBSERVICE_UPDATE, {ATTR_EVENT_WSUPD_TYPE: TRIGGER_UPDATE_DEVICES}
        )
    elif update_type == TRIGGER_UPDATE_SYSTEM_STATE:
        hass.bus.fire(
            EVENT_WEBSERVICE_UPDATE,
            {ATTR_EVENT_WSUPD_TYPE: TRIGGER_UPDATE_SYSTEM_STATE},
        )
    else:
        log_fatal("Unexpected update type: %s" % update_type)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up Teufel Raumfeld from a config entry."""

    def cb_webservice_update(update_type, hass=hass):
        event_on_update(hass, update_type)

    host = entry.data["host"]
    port = entry.data["port"]
    raumfeld = HassRaumfeldHost(host, port)
    host_is_not_valid = not await raumfeld.async_host_is_valid()
    if host_is_not_valid:
        log_error("Invalid host: %s:%s" % (host, port))
        return False
    raumfeld.callback = cb_webservice_update
    log_info("Starting web service update thread")
    raumfeld.start_update_thread()
    log_info("Web service update thread started")
    log_debug("raumfeld.wsd=%s" % raumfeld.wsd)
    hass.data[DOMAIN][entry.entry_id] = raumfeld

    for component in PLATFORMS:
        hass.async_create_task(
            hass.config_entries.async_forward_entry_setup(entry, component)
        )

    def handle_group(call):
        room_lst = call.data.get("room_names")
        raumfeld.create_group(room_lst)

    hass.services.async_register(DOMAIN, SERVICE_GROUP, handle_group)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload a config entry."""
    unload_ok = all(
        await asyncio.gather(
            *[
                hass.config_entries.async_forward_entry_unload(entry, component)
                for component in PLATFORMS
            ]
        )
    )
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


class HassRaumfeldHost(hassfeld.RaumfeldHost):
    """Raumfeld Host class adapted for Home Assistant."""

    def get_groups(self):
        """Get active speaker groups."""
        return self.get_zones()

    def group_is_valid(self, room_lst):
        """Check whether a speaker group according to passed rooms exists."""
        return self.zone_is_valid(room_lst)

    def create_group(self, room_lst):
        """Create a speaker group with rooms passed."""
        self.create_zone(room_lst)

    def set_group_mute(self, room_lst, mute):
        """Create a speaker group with rooms passed."""
        self.set_zone_mute(room_lst, mute)

    def set_group_volume(self, room_lst, raumfeld_vol):
        """Mute the speaker group corresponding to passed rooms."""
        self.set_zone_volume(room_lst, raumfeld_vol)

    def set_group_room_volume(self, room_lst, raumfeld_vol, rooms=None):
        """Set volume of all rooms in a speaker group."""
        self.set_zone_room_volume(room_lst, raumfeld_vol, rooms)

    def group_play(self, room_lst):
        """Play media of speaker group corresponding to passed rooms."""
        self.zone_play(room_lst)

    def group_pause(self, room_lst):
        """Pause media of speaker group corresponding to passed rooms."""
        self.zone_pause(room_lst)

    def group_stop(self, room_lst):
        """Stop media of speaker group corresponding to passed rooms."""
        self.zone_stop(room_lst)

    def group_previous_track(self, room_lst):
        """Jump to previous track on speaker group corresp. to passed rooms."""
        self.zone_previous_track(room_lst)

    def group_next_track(self, room_lst):
        """Jump to next track on speaker group corresp. to passed rooms."""
        self.zone_next_track(room_lst)

    def group_seek(self, room_lst, position):
        """Seek to position on speaker group corresp. to passed rooms."""
        self.zone_seek(room_lst, position)

    def change_group_volume(self, room_lst, volume):
        """Change volume on speaker group corresp. to passed rooms."""
        self.change_zone_volume(room_lst, volume)

    def get_group_volume(self, room_lst):
        """Return volume [0-100] of speaker group corresp. to passed rooms."""
        return self.get_zone_volume(room_lst)

    def get_group_mute(self, room_lst):
        """Return bool mute status of speaker group corresp. to passed rooms."""
        return self.get_zone_mute(room_lst)

    def save_group(self, room_lst):
        """Save media and position of speaker group corresp. to passed rooms."""
        self.save_zone(room_lst)

    def restore_group(self, room_lst):
        """Restore media and position of speaker group corresp. to passed rooms."""
        self.restore_zone(room_lst)

    def search_and_group_play(self, zone_room_lst, search_criteria):
        """Search track and play first hit on speaker group"""
        self.search_and_zone_play(zone_room_lst, search_criteria)

    def _timespan_secs(self, timespan):
        """Parse a time-span into number of seconds."""
        return sum(
            60 ** x[0] * int(x[1]) for x in enumerate(reversed(timespan.split(":")))
        )

    def browse_media(self, object_id=0, browse_flag=None):
        """Browse conent directory and return object as expected by webhook."""
        browse_lst = []
        media_entries = []
        can_play = False
        thumbnail = None
        track_number = 0
        browsable_oid = object_id.split(MEDIA_CONTENT_ID_SEP)[0]
        media_xml = self.browse_media_server(browsable_oid, browse_flag)
        media = xmltodict.parse(
            media_xml, force_list=(DIDL_ELEM_CONTAINER, DIDL_ELEM_ITEM)
        )

        if DIDL_ELEM_CONTAINER in media[DIDL_ELEMENT]:
            media_entries += media[DIDL_ELEMENT][DIDL_ELEM_CONTAINER]
        if DIDL_ELEM_ITEM in media[DIDL_ELEMENT]:
            media_entries += media[DIDL_ELEMENT][DIDL_ELEM_ITEM]

        for entry in media_entries:
            can_expand = True
            supported_oid = False
            media_content_id = entry[DIDL_ATTR_ID]

            if media_content_id not in UNSUPPORTED_OBJECT_IDS:
                # FIXME: Should be removed in favor of checking for UNSUPPORTED_OBJECT_IDS
                if media_content_id in SUPPORTED_OBJECT_IDS:
                    supported_oid = True
                else:
                    for oid_prefix in SUPPORTED_OBJECT_PREFIXES:
                        if media_content_id.startswith(oid_prefix):
                            supported_oid = True
                            break

            if not supported_oid:
                log_info("Unsupported Object ID: %s" % media_content_id)
                continue

            # Workaround: Sometimes XML includes namespaces.
            if DIDL_VALUE in entry[DIDL_ELEM_TITLE]:
                title = title = entry[DIDL_ELEM_TITLE][DIDL_VALUE]
            else:
                title = title = entry[DIDL_ELEM_TITLE]

            # Workaround: Sometimes XML includes namespaces.
            if DIDL_VALUE in entry[DIDL_ELEM_CLASS]:
                media_content_type = entry[DIDL_ELEM_CLASS][DIDL_VALUE]
            else:
                media_content_type = entry[DIDL_ELEM_CLASS]

            if media_content_type.startswith(UPNP_CLASS_AUDIO_ITEM):
                can_expand = False
            if DIDL_ELEM_ART_URI in entry:
                thumbnail = entry[DIDL_ELEM_ART_URI][DIDL_VALUE]

            play_uri = self.mk_play_uri(
                media_content_type, media_content_id, track_number
            )
            media_content_id += MEDIA_CONTENT_ID_SEP + play_uri
            track_number += 1

            browse_lst.append(
                BrowseMedia(
                    title=title,
                    media_class="music",
                    media_content_id=media_content_id,
                    media_content_type=media_content_type,
                    can_play=can_play,
                    can_expand=can_expand,
                    thumbnail=thumbnail,
                )
            )
        return browse_lst

    def get_track_info(self, zone_room_lst):
        """Return data to update media information."""
        position_info = self.get_position_info(zone_room_lst)
        metadata_xml = position_info[POSINF_ELEM_TRACK_DATA]

        track_info = {
            TRACKINF_TITLE: None,
            TRACKINF_ARTIST: None,
            TRACKINF_IMGURI: None,
            TRACKINF_ALBUM: None,
        }

        track_info["number"] = position_info[POSINF_ELEM_TRACK]
        track_info["duration"] = self._timespan_secs(
            position_info[POSINF_ELEM_DURATION]
        )
        track_info["uri"] = position_info[POSINF_ELEM_URI]
        track_info["position"] = self._timespan_secs(
            position_info[POSINF_ELEM_ABS_TIME]
        )

        if metadata_xml is not None:
            metadata = xmltodict.parse(metadata_xml)
            if DIDL_ELEM_TITLE in metadata[DIDL_ELEMENT][DIDL_ELEM_ITEM]:
                track_info[TRACKINF_TITLE] = metadata[DIDL_ELEMENT][DIDL_ELEM_ITEM][
                    DIDL_ELEM_TITLE
                ]
            if DIDL_ELEM_ARTIST in metadata[DIDL_ELEMENT][DIDL_ELEM_ITEM]:
                track_info[TRACKINF_ARTIST] = metadata[DIDL_ELEMENT][DIDL_ELEM_ITEM][
                    DIDL_ELEM_ARTIST
                ]
            if DIDL_ELEM_ART_URI in metadata[DIDL_ELEMENT][DIDL_ELEM_ITEM]:
                if (
                    DIDL_VALUE
                    in metadata[DIDL_ELEMENT][DIDL_ELEM_ITEM][DIDL_ELEM_ART_URI]
                ):
                    track_info[TRACKINF_IMGURI] = metadata[DIDL_ELEMENT][
                        DIDL_ELEM_ITEM
                    ][DIDL_ELEM_ART_URI][DIDL_VALUE]
            if DIDL_ELEM_ALBUM in metadata[DIDL_ELEMENT][DIDL_ELEM_ITEM]:
                track_info[TRACKINF_ALBUM] = metadata[DIDL_ELEMENT][DIDL_ELEM_ITEM][
                    DIDL_ELEM_ALBUM
                ]

        return track_info

    def mk_play_uri(self, media_type, media_id, track_number=0):
        """Create a valid URI playable by raumfeld media renderer."""
        if media_type in [
            UPNP_CLASS_ALBUM,
            UPNP_CLASS_PLAYLIST_CONTAINER,
            UPNP_CLASS_PODCAST_EPISODE,
            UPNP_CLASS_TRACK,
        ]:
            media_server_udn = self.media_server_udn

            play_uri = (
                "dlna-playcontainer://"
                + urllib.parse.quote(media_server_udn)
                + "?sid="
                + urllib.parse.quote(URN_CONTENT_DIRECTORY)
                + "&cid="
            )

            if media_type in [UPNP_CLASS_ALBUM, UPNP_CLASS_PLAYLIST_CONTAINER]:
                play_uri += urllib.parse.quote(media_id, safe="")
            elif media_type in [UPNP_CLASS_PODCAST_EPISODE, UPNP_CLASS_TRACK]:
                container_id = media_id.rsplit("/", 1)[0]
                play_uri += urllib.parse.quote(container_id, safe="")

            play_uri += "&md=0"

            if media_type in [UPNP_CLASS_TRACK, UPNP_CLASS_PODCAST_EPISODE]:
                track_number = str(track_number)
                play_uri += (
                    "&fid="
                    + urllib.parse.quote(media_id, safe="")
                    + "&fii="
                    + track_number
                )

            return play_uri
        if media_type == UPNP_CLASS_RADIO:
            media_server_udn = self.media_server_udn

            play_uri = (
                "dlna-playsingle://"
                + urllib.parse.quote(media_server_udn)
                + "?sid="
                + urllib.parse.quote(URN_CONTENT_DIRECTORY)
                + "&iid="
            )

            play_uri += urllib.parse.quote(media_id, safe="")
            return play_uri
        if media_type == UPNP_CLASS_LINE_IN:
            play_uri = "http://10.0.107.17:8888/stream.flac"
            return play_uri
        else:
            log_info(
                "Building of playable URI for media type '%s' not needed or not implemented"
                % media_type
            )
            return media_id
