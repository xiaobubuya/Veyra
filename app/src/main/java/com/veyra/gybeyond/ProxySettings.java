package com.veyra.gybeyond;

import android.content.Context;
import android.content.SharedPreferences;

/**
 * 黄果网络通道设置（仅黄果/私密模式生效；红果永远直连，不走本设置）。
 * 两态模式（无自动判定，显式选择，切换立即生效）：
 *   MODE_DIRECT  仅直连：只用系统网络栈（VPN/全局代理自然生效），失败即报错
 *   MODE_PROXY   仅代理：只用配置的代理地址，失败即报错
 *
 * 「走后端转发」（MODE_BACKEND=3：内容全经后端 /api/huangguo-proxy 转发）已移除——
 * 后端不再替客户端抓源站。旧存档里的 3（以及更早的 0=自动）一律归一到 MODE_DIRECT。
 * MODE_BACKEND 常量只为源码兼容保留，不再可能被选中，也不会从 {@link #mode} 返回。
 *
 * 每次请求实时读取，切换模式立即生效（无需重建/重启）。默认仅直连。
 */
final class ProxySettings {
    private static final String PREFS = "chengzi-settings";
    private static final String KEY = "huangguoProxy";
    private static final String KEY_MODE = "huangguoMode";

    static final int MODE_DIRECT = 1;
    static final int MODE_PROXY = 2;
    /** @deprecated 走后端转发已移除，仅为旧引用保留；{@link #mode} 永不返回此值。 */
    @Deprecated
    static final int MODE_BACKEND = 3;

    private ProxySettings() { }

    /** 当前代理地址，未设置返回空字符串。 */
    static String address(Context context) {
        return context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).getString(KEY, "").trim();
    }

    static void set(Context context, String address) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
                .edit().putString(KEY, String.valueOf(address).trim()).apply();
    }

    /** 当前黄果通道模式（1 直连 / 2 代理）。旧版 0=自动、3=走后端转发 一并归一到仅直连。 */
    static int mode(Context context) {
        int mode = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).getInt(KEY_MODE, MODE_DIRECT);
        return mode == MODE_PROXY ? MODE_PROXY : MODE_DIRECT;
    }

    static void setMode(Context context, int mode) {
        int next = mode == MODE_PROXY ? MODE_PROXY : MODE_DIRECT;
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit().putInt(KEY_MODE, next).apply();
    }
}
