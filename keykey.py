#!/usr/bin/env python2

"""
HACKS to replace slate.js with wmiface / wmctrl / xdotool commands.

TODO replace wmiface with combination of xdotool, xwinfo, xprop...
eg. see second answer part of
http://unix.stackexchange.com/a/156349/84607
which can be  simplified (easier to parse in python than bash+sed)
"""

import subprocess
import re

LEFT = 'left'
RIGHT = 'right'
UP = 'up'
DOWN = 'down'
TOP = 'top'
BOTTOM = 'bottom'

geom_re = re.compile(r'(\d+)x(\d+)\+(-?\d+)\+(-?\d+)')


def _as_hex(intstring):
    return hex(int(intstring)).replace('0x', '0x0')


def _as_intstring(hexstring):
    hexstring = hexstring.split('x', 1)[-1]
    return str(int(hexstring, 16))


def get_window_list():
    """
    Get geometries of all windows on current workspace.
    """
    out = subprocess.check_output(['wmiface', 'normalWindows', '1'])
    window_ids = out.splitlines()

    # Convenience borders.
    windows = []
    for w_id in window_ids:
        out = subprocess.check_output(['wmiface', 'frameGeometry', w_id])
        # eg. 650x437+0+-31
        width, height, x, y = map(int, geom_re.match(out).groups())
        w = {'id': w_id,
             'hex_id': _as_hex(w_id)}
        windows.append(w)
        w['width'] = width
        w['height'] = height
        w[LEFT] = w['x'] = x
        w[TOP] = w['y'] = y
        w[RIGHT] = w['x'] + w['width']
        w[BOTTOM] = w['y'] + w['height']

    return windows


def get_active_desktop_id():
    # NOTE wmctrl and xdotool count from 0, wmiface counts from 1.
    out = subprocess.check_output(['wmctrl', '-d'])
    desktops = [d.split(None, 9) for d in out.splitlines()]
    for d in desktops:
        if d[1] == '*':
            return d[0]
    raise RuntimeError("Can't determine active desktop")


def get_active_window_hex_id():
    """
    Get hex id of currently active window.
    """
    out = subprocess.check_output(['wmiface', 'activeWindow'])
    return _as_hex(out.strip())


def get_desktop_borders(desktop_id=None):
    if desktop_id is None:
        desktop_id = get_active_desktop_id()
    # TRBL order ... css has ruined me.
    out = subprocess.check_output(['wmctrl', '-d'])
    desktops = [d.split(None, 9) for d in out.splitlines()]
    desktop_dicts = []
    for d in desktops:
        desktop = {'id': d[0],
                   'active': True if d[1] == '*' else False,
                   }
        # We use the "workspace" area, eg. not including the WM panel.
        workarea_x, workarea_y = map(int, d[7].split(','))
        workarea_w, workarea_h = map(int, d[8].split('x'))
        desktop[TOP] = workarea_y
        desktop[LEFT] = workarea_x
        desktop[RIGHT] = workarea_x + workarea_w
        desktop[BOTTOM] = workarea_y + workarea_h
        desktop_dicts.append(desktop)

        if desktop['id'] == desktop_id:
            return (desktop[TOP],
                    desktop[RIGHT],
                    desktop[BOTTOM],
                    desktop[LEFT],
                    )
    raise ValueError("No desktop %d" % desktop_id)


def get_window_info_by_id(window_id):
    """
    Return geometry info for the specified window (int or hex).
    """
    windows = get_window_list()
    windows = [w for w in windows if window_id in (w['id'], w['hex_id'])]
    if len(windows) == 1:
        return windows[0]
    elif len(windows) > 1:
        raise RuntimeError("Too many matching windows, should never happen. %s"
                           % window_id)
    else:
        raise RuntimeError("Couldn't find window %s" % window_id)


def get_all_window_borders(desktop_id=None, include_desktop=True,
                           include_center=True,
                           _windowlist=None):
    if desktop_id is None:
        desktop_id = get_active_desktop_id()

    if _windowlist is None:
        windows = get_window_list()
    else:
        windows = _windowlist

    x_borders = set()
    y_borders = set()
    top, right, bottom, left = get_desktop_borders(desktop_id)

    def maybe_add_x(x):
        # print "X:", left, x, right
        if left <= x <= right:
            x_borders.add(x)

    def maybe_add_y(y):
        # print "Y:", top, y, bottom
        if top <= y <= bottom:
            y_borders.add(y)

    for w in windows:
        maybe_add_x(w[LEFT])
        maybe_add_x(w[RIGHT])
        maybe_add_y(w[TOP])
        maybe_add_y(w[BOTTOM])

    if include_desktop:
        x_borders.add(left)
        x_borders.add(right)
        y_borders.add(top)
        y_borders.add(bottom)
        if include_center:
            center_x = (right - left) // 2
            maybe_add_x(center_x)
            center_y = (bottom - top) // 2
            maybe_add_y(center_y)

    x_borders = sorted(x_borders)
    y_borders = sorted(y_borders)
    return (x_borders, y_borders)


def move_to_next_window_edge(window_id, direction):
    windows = get_window_list()

    for i, win in enumerate(windows):
        if window_id in (win['id'], win['hex_id']):
            print "Active window: %sx%s+%s+%s" % (win['width'], win['height'],
                                                  win[LEFT], win[TOP])
            # Don't include it in get_all_window_borders()
            windows.pop(i)
            break
    else:
        raise RuntimeError("Active window not found")

    x_borders, y_borders = get_all_window_borders(
        include_desktop=True, include_center=True,
        _windowlist=windows)

    d_top, d_right, d_bottom, d_left = get_desktop_borders()

    # Centering the window has to be done in this func. because it depends
    # on dimensions of THIS window, which get_all_window_borders
    # doesn't know.
    d_center_x = (d_right - d_left) // 2
    d_center_y = (d_bottom - d_top) // 2

    if direction in (RIGHT, LEFT):
        win_edge_1 = win[LEFT]
        span = win['width']
        candidates = x_borders
        edge_to_center_1 = d_center_x - (span // 2)
    elif direction in (UP, DOWN):
        win_edge_1 = win[TOP]
        span = win['height']
        candidates = y_borders
        edge_to_center_1 = d_center_y - (span // 2)
    else:
        raise ValueError(u"Invalid direction %s" % direction)

    if direction == RIGHT:
        def is_valid(x):
            return x > win_edge_1 and x <= (d_right - span)
    elif direction == LEFT:
        def is_valid(x):
            return x < win_edge_1 and x >= d_left
    elif direction == UP:
        def is_valid(y):
            return y < win_edge_1 and y >= d_top
    elif direction == DOWN:
        def is_valid(y):
            return y > win_edge_1 and y <= (d_bottom - span)

    # Allow snapping to both sides of an edge.
    candidates.extend([c - span for c in candidates])
    # Allow snapping to exact screen center.
    # This is after the previous line on purpose -
    # don't want to snap to center + 1/2 span for no reason.
    candidates.append(edge_to_center_1)

    candidates = sorted(set(candidates))
    candidates = [c for c in candidates if is_valid(c)]

    print "Candidates are: ", candidates

    if candidates:
        if direction == RIGHT:
            move_window_to(window_id, candidates[0], win[TOP])
        if direction == LEFT:
            move_window_to(window_id, candidates[-1], win[TOP])
        if direction == UP:
            move_window_to(window_id, win[LEFT], candidates[-1])
        if direction == DOWN:
            move_window_to(window_id, win[LEFT], candidates[0])


def move_window_to(window_id, x=-1, y=-1):
    mvarg = '0,%d,%d,-1,-1' % (x, y)
    # mvarg = '1,%d,%d,-1,-1' % (x, y)   # experiment w/ gravity
    # XXX TODO use `wmiface frameGeometry id x y` where id is int
    cmd = ['wmctrl', '-i', '-r', window_id, '-e', mvarg]
    out = subprocess.check_output(cmd)
    print ' '.join(cmd), "...with output:", out


# TODO another command to maximize to next edge?

# TODO another command to emulate 'focus right' et al. from slate

if __name__ == '__main__':
    # pprint.pprint(get_desktop_borders())
    # pprint.pprint(get_all_window_borders())
    win_id = get_active_window_hex_id()
    import sys
    direction = sys.argv[1]
    print "==== %s ============" % direction
    move_to_next_window_edge(win_id, direction)
