package com.zerowaste.grocery.util;

/** Small helpers for cleaning optional query parameters. */
public final class Params {

    private Params() {
    }

    /** Blank or missing becomes null; otherwise trimmed. */
    public static String text(String s) {
        if (s == null || s.isBlank()) {
            return null;
        }
        return s.trim();
    }

    /** Like text(), but upper-cased (store and SKU ids are stored in upper case). */
    public static String id(String s) {
        String t = text(s);
        return t == null ? null : t.toUpperCase();
    }
}
