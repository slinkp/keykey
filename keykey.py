#!/usr/bin/env python2

"""
HACKS to replace slate.js with wmiface / wmctrl / xdotool commands.

TODO replace wmiface with combination of xdotool, xwinfo, xprop...
eg. see second answer part of
http://unix.stackexchange.com/a/156349/84607
which can be  simplified (easier to parse in python than bash+sed)
"""

import collections
import subprocess
import re

LEFT = 'left'
RIGHT = 'right'
UP = 'up'
DOWN = 'down'
TOP = 'top'
BOTTOM = 'bottom'


class WMIFace(object):

    # eg. 650x437+0+-31
    _geom_re = re.compile(r'(\d+)x(\d+)\+(-?\d+)\+(-?\d+)')

    @staticmethod
    def get_window_ids():
        out = subprocess.check_output(['wmiface', 'normalWindows', '1'])
        window_ids = out.splitlines()
        return window_ids

    @classmethod
    def get_window_dimensions(cls, window_id):
        """
        Given a window id, return a WindowGeometry
        """
        out = subprocess.check_output(['wmiface', 'frameGeometry', window_id])
        width, height, x, y = map(int, cls._geom_re.match(out).groups())
        geom = WindowGeometry(
            id=window_id,
            width=width,
            height=height,
            x=x,
            y=y,
            left=x,
            top=y,
            right=x + width,
            bottom=y + height,
            )
        return geom

    @staticmethod
    def get_active_window_id():
        out = subprocess.check_output(['wmiface', 'activeWindow'])
        return out.strip()

    @classmethod
    def get_window_geometries(cls, window_ids):
        """
        Get list of WindowGeometry for all the given window ids.
        """
        # Convenience borders.
        windows = []
        for w_id in window_ids:
            geom = cls.get_window_dimensions(w_id)
            windows.append(geom)
        return windows


WindowGeometry = collections.namedtuple(
    'WindowGeometry',
    ['id', 'width', 'height', 'x', 'y', LEFT, TOP, RIGHT, BOTTOM]
)


class WMCtrl(object):

    @staticmethod
    def get_active_desktop_id():
        # NOTE wmctrl and xdotool count from 0, wmiface counts from 1.
        out = subprocess.check_output(['wmctrl', '-d'])
        desktops = [d.split(None, 9) for d in out.splitlines()]
        for d in desktops:
            if d[1] == '*':
                return d[0]
        raise RuntimeError("Can't determine active desktop")

    @staticmethod
    def move_window_to(window_id, x=-1, y=-1):
        mvarg = '0,%d,%d,-1,-1' % (x, y)
        # mvarg = '1,%d,%d,-1,-1' % (x, y)   # experiment w/ gravity
        cmd = ['wmctrl', '-i', '-r', window_id, '-e', mvarg]
        out = subprocess.check_output(cmd)
        print ' '.join(cmd), "...with output:", out

    @staticmethod
    def get_desktop_borders(desktop_id):
        # TRBL order ... css has ruined me.
        out = subprocess.check_output(['wmctrl', '-d'])
        desktops = [d.split(None, 9) for d in out.splitlines()]
        desktop_dicts = []
        for d in desktops:
            desktop = {
                'id': d[0],
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
                return (
                    desktop[TOP],
                    desktop[RIGHT],
                    desktop[BOTTOM],
                    desktop[LEFT],
                )
        raise ValueError("No desktop %d" % desktop_id)


def get_interesting_edges(desktop_borders, include_desktop=True,
                          include_center=True,
                          windowlist=None):
    windows = windowlist

    x_borders = set()
    y_borders = set()
    top, right, bottom, left = desktop_borders

    def maybe_add_x(x):
        # print "X:", left, x, right
        if left <= x <= right:
            x_borders.add(x)

    def maybe_add_y(y):
        # print "Y:", top, y, bottom
        if top <= y <= bottom:
            y_borders.add(y)

    for w in windows:
        maybe_add_x(w.left)
        maybe_add_x(w.right)
        maybe_add_y(w.top)
        maybe_add_y(w.bottom)

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


class WindowMover(object):

    """
    Object responsible for moving windows
    """
    def __init__(
            self,
            move_window=None,
            get_window_ids=None,
            get_active_desktop_id=None,
            get_desktop_borders=None,
            get_window_geometries=None,
            ):
        self.move_window = move_window
        self.get_window_ids = get_window_ids
        self.get_active_desktop_id = get_active_desktop_id
        self.get_desktop_borders = get_desktop_borders
        self.get_window_geometries = get_window_geometries

    def move_to_next_window_edge(self, window_id, direction):
        all_ids = self.get_window_ids()
        windows = self.get_window_geometries(all_ids)

        for i, win in enumerate(windows):
            if window_id == win.id:
                print "Active window: %sx%s+%s+%s" % (win.width, win.height,
                                                      win.left, win.top)
                # Don't include it in get_interesting_edges()
                windows.pop(i)
                break
        else:
            raise RuntimeError("Active window not found")

        desktop_id = self.get_active_desktop_id()
        desktop_borders = self.get_desktop_borders(desktop_id)
        x_borders, y_borders = get_interesting_edges(
            desktop_borders=desktop_borders,
            include_desktop=True, include_center=True,
            windowlist=windows)

        d_top, d_right, d_bottom, d_left = desktop_borders

        # Centering the window has to be done in this func. because it depends
        # on dimensions of THIS window, which get_interesting_edges
        # doesn't know.
        d_center_x = (d_right - d_left) // 2
        d_center_y = (d_bottom - d_top) // 2

        if direction in (RIGHT, LEFT):
            win_edge_1 = win.left
            span = win.width
            candidates = x_borders
            edge_to_center_1 = d_center_x - (span // 2)
        elif direction in (UP, DOWN):
            win_edge_1 = win.top
            span = win.height
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
                self.move_window(window_id, candidates[0], win.top)
            if direction == LEFT:
                self.move_window(window_id, candidates[-1], win.top)
            if direction == UP:
                self.move_window(window_id, win.left, candidates[-1])
            if direction == DOWN:
                self.move_window(window_id, win.left, candidates[0])


# TODO another command to maximize to next edge?

# TODO another command to emulate 'focus right' et al. from slate

if __name__ == '__main__':
    import sys
    direction = sys.argv[1]
    print "==== %s ============" % direction
    win_id = WMIFace.get_active_window_id()
    mover = WindowMover(
        move_window=WMCtrl.move_window_to,
        get_window_ids=WMIFace.get_window_ids,
        get_window_geometries=WMIFace.get_window_geometries,
        get_active_desktop_id=WMCtrl.get_active_desktop_id,
        get_desktop_borders=WMCtrl.get_desktop_borders,
    )
    mover.move_to_next_window_edge(win_id, direction)
