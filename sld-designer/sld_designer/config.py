"""Shared constants. They are served to the browser editor via /api/config so
that the on-screen drawing and the PDF/DXF export use exactly the same values."""

APP_NAME = "SLD Designer"
VERSION = "1.0.0"

PROJECT_FORMAT = "SLD-CAD"      # value of the "format" key inside every .cad file
PROJECT_VERSION = 1
LIBRARY_FORMAT = "SLD-LIB"      # value of the "format" key inside every .sldlib file
LIBRARY_VERSION = 1

# Sheet sizes in mm (landscape: width, height)
SHEETS = {
    "A4": [297, 210],
    "A3": [420, 297],
    "A2": [594, 420],
    "A1": [841, 594],
    "A0": [1189, 841],
}

# All lengths are millimetres on the printed sheet.
STYLE = {
    "line_w": 0.35,        # symbols and wires
    "bus_w": 1.4,          # busbars
    "border_w": 0.7,       # sheet frame
    "tb_w": 0.35,          # title block grid
    "junction_r": 0.9,     # junction dot radius
    "tag_size": 3.5,       # font size (em, mm) of the element tag
    "attr_size": 3.0,      # font size of attribute lines / wire labels
    "text_size": 3.5,      # default size of free text
    "pitch": 4.2,          # line pitch of multi-line labels
    "label_gap": 2.0,      # distance between symbol and its label
    "margin": 10,          # frame inset from the sheet edge
    "dash": [2.0, 1.2],    # dash pattern (mm) for dashed lines
    "arc_step": 10,        # degrees per segment when flattening arcs
    "grids": [1, 2.5, 5, 10],
}

# Title block, anchored to the bottom-right corner of the frame.
# cell = [x, y, w, h, key, caption]  (relative to the block's top-left corner)
TITLEBLOCK = {
    "w": 180,
    "h": 36,
    "cells": [
        [0, 0, 110, 12, "project", "PROJECT"],
        [110, 0, 70, 12, "number", "DRAWING NO."],
        [0, 12, 110, 12, "title", "TITLE"],
        [110, 12, 20, 12, "rev", "REV."],
        [130, 12, 50, 12, "date", "DATE"],
        [0, 24, 90, 12, "company", "COMPANY"],
        [90, 24, 30, 12, "drawn", "DRAWN"],
        [120, 24, 30, 12, "checked", "CHECKED"],
        [150, 24, 15, 12, "scale", "SCALE"],
        [165, 24, 15, 12, "sheet", "SHEET"],
    ],
    "caption_size": 1.8,
    "value_size": 3.2,
}

PRIM_TYPES = ("line", "poly", "rect", "circle", "arc", "text")
ELEMENT_TYPES = ("sym", "bus", "rect", "line", "text")
