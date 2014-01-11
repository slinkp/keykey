"""
HACKS to replace slate.js with ewmh commands.

TODO try  https://github.com/BurntSushi/xpybutil which is not pip-installable.  It provides an ewmh library.

TODO is there any way to get geometries that INCLUDE the WM chrome??
 - Maybe wmiface (depends on Qt core).


 http://python-xlib.sourceforge.net/?page=documentation
 
"""

import subprocess
import pprint


def get_window_list():
    out = subprocess.check_output(['wmctrl', '-l', '-p', '-x', '-G'])
    windows = [w.split(None, 9) for w in out.splitlines()]
    windows = [{'id': w[0], 'desktop': w[1], 'pid': w[2],
                'x': int(w[3]), 'y': int(w[4]),
                'width': int(w[5]), 'height': int(w[6]),
                'wm_class': w[7], 'title': w[8]
                } for w in windows]

    # Convenience borders.
    for w in windows:
        w['top'] = w['y']
        w['right'] = w['x'] + w['width']
        w['bottom'] = w['y'] + w['height']
        w['left'] = w['x']

    return windows


def get_active_desktop_id():
    out = subprocess.check_output(['wmctrl', '-d'])
    desktops = [d.split(None, 9) for d in out.splitlines()]
    for d in desktops:
        if d[1] == '*':
            return d[0]
    raise RuntimeError("Can't determine active desktop")


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
        desktop['top'] = workarea_y
        desktop['left'] = workarea_x
        desktop['right'] = workarea_x + workarea_w
        desktop['bottom'] = workarea_y + workarea_h
        desktop_dicts.append(desktop)

        if desktop['id'] == desktop_id:
            return (desktop['top'],
                    desktop['right'],
                    desktop['bottom'],
                    desktop['left'],
                    )
    raise ValueError("No desktop %d" % desktop_id)


def get_window(window_id):
    window = [w for w in get_window_list() if w['id'] == window_id][0]
    return window


def get_all_window_borders(desktop_id=None):
    if desktop_id is None:
        desktop_id = get_active_desktop_id()
    windows = get_window_list()
    windows = [w for w in windows if w['desktop'] == desktop_id]
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
        maybe_add_x(w['left'])
        maybe_add_x(w['right'])
        maybe_add_y(w['top'])
        maybe_add_y(w['bottom'])
    x_borders = sorted(x_borders)
    y_borders = sorted(y_borders)
    return (x_borders, y_borders)


def move_to_next_window_edge(window_id, direction):
    win = get_window(window_id)
    x_borders, y_borders = get_all_window_borders()
    d_top, d_right, d_bottom, d_left = get_desktop_borders()
    distances = []
    if direction == 'right':
        win_edge_1 = win['left']
        win_edge_2 = win['right']
        borders = x_borders
        validate = lambda a, b: a > b and (a - b + win['right'] <= d_right)
        reverse_distances = False
    elif direction == 'left':
        win_edge_1 = win['left']
        win_edge_2 = win['right']
        borders = reversed(x_borders)
        validate = lambda a, b: a < b and (a - b + win['left'] >= d_left)
        reverse_distances = True
    elif direction == 'down':
        win_edge_1 = win['top']
        win_edge_2 = win['bottom']
        borders = y_borders
        validate = lambda a, b: a > b and (a - b + win['bottom'] <= d_bottom)
        reverse_distances = False
    elif direction == 'up':
        win_edge_1 = win['top']
        win_edge_2 = win['bottom']
        borders = reversed(y_borders)
        validate = lambda a, b: a < b and (a - b + win['top'] >= d_top)
        reverse_distances = True
    else:
        raise ValueError("Direction was %r" % direction)

    for edge in borders:
        if validate(edge, win_edge_1):
            distances.append(edge - win_edge_1)
        if validate(edge, win_edge_2):
            distances.append(edge - win_edge_2)

    MIN_DISTANCE = 12  # XXX hack for fvwm not including window chrome :(
    distances = [d for d in distances if abs(d) >= MIN_DISTANCE]
    distances.sort(reverse=reverse_distances)
    print "Distances: "
    pprint.pprint(distances)
    if not distances:
        print "NOwhere to move"
        return

    def move(x, y):
        print "WOULD MOVE TO: %d, %d" % (x, y)

    if direction in ("left", "right"):
        move_window_to(window_id, x=win['left'] + distances[0])
    else:
        move_window_to(window_id, y=win['top'] + distances[0])


def move_window_to(window_id, x=-1, y=-1):
    # mvarg = '0,%d,%d,-1,-1' % (x, y)
    mvarg = '1,%d,%d,-1,-1' % (x, y)   # experiment w/ gravity
    cmd = ['wmctrl', '-i', '-r', window_id, '-e', mvarg]
    out = subprocess.check_output(cmd)
    print ' '.join(cmd), "...with output:", out

if __name__ == '__main__':
    pprint.pprint(get_desktop_borders())
    pprint.pprint(get_all_window_borders())
    WIN_ID = '0x02c00177'

    import sys
    direction = sys.argv[1]
    print "==== %s ============" % direction
    move_to_next_window_edge(WIN_ID, direction)
