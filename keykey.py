#!/usr/bin/env python2

"""
HACKS to replace slate.js with wmiface / wmctrl / xdotool commands.

wmiface comes from KDE, but ports of it to eg. ubuntu or xubuntu
seem to be unmaintained, so this has been abstracted to
swap out other commands.
"""

# Some of this came from
# eg. second answer part of
# http://unix.stackexchange.com/a/156349/84607
# which can be simplified (easier to parse in python than bash+sed)

import abc
import collections
import re
import subprocess


LEFT = 'left'
RIGHT = 'right'
UP = 'up'
DOWN = 'down'
TOP = 'top'
BOTTOM = 'bottom'


def _as_hex(intstring):
    return hex(int(intstring)).replace('0x', '0x0')


def _as_intstring(hexstring):
    hexstring = hexstring.split('x', 1)[-1]
    return str(int(hexstring, 16))


class AbstractWindowInfoService(object):

    __metaclass__ = abc.ABCMeta

    @abc.abstractmethod
    def get_window_ids(self, desktop_id):
        """
        return list of integer IDs for the given desktop ID.

        Some implementations may ignore the desktop_id parameter
        and use the current desktop.
        """

    @abc.abstractmethod
    def get_window_dimensions(window_id):
        """
        Given a window id, return a WindowGeometry
        """

    @abc.abstractmethod
    def get_active_window_id():
        """
        Return integer ID for currently active window.
        """

    @classmethod
    def get_window_geometries(cls, window_ids):
        """
        Get list of WindowGeometry for all the given window ids.
        """
        # Convenience borders.
        windows = []
        for w_id in window_ids:
            geom = cls.get_window_dimensions(w_id)
            if geom is not None:
               windows.append(geom)
        return windows


class WMIFace(AbstractWindowInfoService):

    # eg. 650x437+0+-31
    _geom_re = re.compile(r'(\d+)x(\d+)\+(-?\d+)\+(-?\d+)')

    @staticmethod
    def get_window_ids(desktop_id):
        # 1 = current desktop;  0 = all non-sticky windows afaict.
        # but since we get no indication of which desktop they're on,
        # we just use current desktop.
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


class NewWindowInfo(AbstractWindowInfoService):

    _left_re = re.compile(r'Absolute upper-left X:\s+([-\d]+)')
    _top_re = re.compile(r'Absolute upper-left Y:\s+([-\d]+)')
    _width_re = re.compile(r'Width:\s+(\d+)')
    _height_re = re.compile(r'Height:\s+(\d+)')
    _extents_re = re.compile(r'Frame extents:\s+(\d+), (\d+), (\d+), (\d+)')

    @staticmethod
    def get_window_ids(desktop_id):
        """
        return list of integer IDs, for given desktop
        """
        out = subprocess.check_output(['wmctrl', '-l'])
        window_ids = []
        for line in out.splitlines():
            if not line.strip():
                continue
            parts = line.split()
            if parts[1] != desktop_id:
                continue
            window_ids.append(str(int(parts[0], 16)))
        return window_ids

    @classmethod
    def get_window_dimensions(cls, window_id):
        """
        Given a window id, return a WindowGeometry
        """
        out = subprocess.check_output(['xwininfo', '-id', window_id])
        width = int(cls._width_re.search(out).group(1))
        height = int(cls._height_re.search(out).group(1))
        left = int(cls._left_re.search(out).group(1))
        top = int(cls._top_re.search(out).group(1))

        # Add offsets for window manager decorations.
        extents_out = subprocess.check_output(
            ['xwininfo', '-id', window_id, '-wm'])
        extents_match = cls._extents_re.search(extents_out)
        if extents_match is None:
            # XXX TODO: happens with some windows eg. hidden ones
            return None
        margin_l, margin_r, margin_t, margin_b = [
            int(n) for n in extents_match.groups()
        ]
        x = left - margin_l
        y = top - margin_t
        width += margin_l + margin_r
        height += margin_t + margin_b

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
        """
        Return integer ID for currently active window.
        """
        out = subprocess.check_output(['xdotool', 'getactivewindow'])
        return out.strip()


WindowGeometry = collections.namedtuple(
    'WindowGeometry',
    ['id', 'width', 'height', 'x', 'y', LEFT, TOP, RIGHT, BOTTOM]
)


class AbstractDesktopService(object):

    __metaclass__ = abc.ABCMeta

    @abc.abstractmethod
    def get_active_desktop_id(self):
        """
        In multi-desktop environments, identify which desktop we're on.
        """

    @abc.abstractmethod
    def get_desktop_borders(self, desktop_id):
        """
        Get the borders of the given desktop, as a tuple
        of (top, right, bottom, left).
        """

    @abc.abstractmethod
    def move_window_to(self, window_id, x=-1, y=-1):
        """
        Move the window such that left edge = x and top edge = y.
        """


class WMCtrl(AbstractDesktopService):

    def __init__(self, translate_ids=False):
        desktop_info = subprocess.check_output(['wmctrl', '-m'])
        self.is_compiz = 'Name: Compiz' in desktop_info
        self.translate_ids = self.is_compiz

    def prepare_window_id(self, id):
        if self.translate_ids:
            return _as_hex(id)
        return id

    @staticmethod
    def get_active_desktop_id():
        # NOTE wmctrl and xdotool count from 0, wmiface counts from 1.
        out = subprocess.check_output(['wmctrl', '-d'])
        desktops = [d.split(None, 9) for d in out.splitlines()]
        for d in desktops:
            if d[1] == '*':
                return d[0]
        raise RuntimeError("Can't determine active desktop")

    def move_window_to(self, window_id, x=-1, y=-1):
        # XXX TODO: Any way to compensate for compiz shadow on panel?  Seems to
        # create a 10px border that I can move into manually, but not with
        # wmctrl.  e.g. if height of panel is 24, and I move to y=24, then I
        # actually end up at y=34.  But mouse can move window to y=24!
        # Likewise, there is a 10px left padding that I can't move beyond but
        # ONLY on the leftmost workspace... on other workspaces I can get to
        # x=0.

        mvarg = '0,%d,%d,-1,-1' % (x, y)
        # mvarg = '1,%d,%d,-1,-1' % (x, y)   # experiment w/ gravity
        # XXX TODO - why under compiz do we need hex ids here but
        # get int ids listed?
        # XXX should we be translating when listing instead?
        window_id = self.prepare_window_id(window_id)
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

        # XXX TODO: for compiz, we should filter out windows on
        # another viewport,
        # i.e. here's a diff of viewing window on 2 from 1 vs. on 2 from 2.
        # Everything's the same except left X is 1727 instead of 47. 
#        """
#<   Absolute upper-left X:  1727
#---
#>   Absolute upper-left X:  47
#22,23c22,23
#<   Corners:  +1727+52  --779+52  --779-588  +1727-588
#<   -geometry 80x24+1717+14
#---
#>   Corners:  +47+52  -901+52  -901-588  +47-588
#>   -geometry 80x24+37+14

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
        desktop_id = self.get_active_desktop_id()
        all_ids = self.get_window_ids(desktop_id)
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

    desktop_svc = WMCtrl()
    win_svc = NewWindowInfo()
    # print win_svc.get_window_dimensions(win_svc.get_active_window_id())
    # print win_svc.get_window_ids()
    # print WMIFace.get_window_ids()

    mover = WindowMover(
        move_window=desktop_svc.move_window_to,
        get_window_ids=win_svc.get_window_ids,
        get_window_geometries=win_svc.get_window_geometries,
        get_active_desktop_id=desktop_svc.get_active_desktop_id,
        get_desktop_borders=desktop_svc.get_desktop_borders,
    )
    win_id = win_svc.get_active_window_id()
    mover.move_to_next_window_edge(win_id, direction)
