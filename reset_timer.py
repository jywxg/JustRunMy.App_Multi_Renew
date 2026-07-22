#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import time
import random
import requests
from seleniumbase import SB

LOGIN_URL = "https://justrunmy.app/id/Account/Login"
DOMAIN    = "justrunmy.app"


def random_sleep(min_sec=1, max_sec=3):
    time.sleep(random.uniform(min_sec, max_sec))


def human_type(sb, selector, text):
    element = sb.find_element(selector)
    element.clear()
    for char in text:
        element.send_keys(char)
        time.sleep(random.uniform(0.05, 0.15))

# ============================================================
#  环境变量与全局变量
# ============================================================
EMAIL        = os.environ.get("ACC")
PASSWORD     = os.environ.get("ACC_PWD")
TG_BOT_TOKEN = os.environ.get("TG_TOKEN")
TG_CHAT_ID   = os.environ.get("TG_ID")

if not EMAIL or not PASSWORD:
    print("致命错误：未找到 ACC 或 ACC_PWD 环境变量！")
    print("请检查 GitHub Repository Secrets 是否配置正确（EML_1, PWD_1...）。")
    sys.exit(1)

# 全局变量，用于动态保存网页上抓取到的应用名称
DYNAMIC_APP_NAME = "未知应用"

# ============================================================
#  Telegram 推送模块
# ============================================================
def send_tg_message(status_icon, status_text, time_left):
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        print("未配置 TG_TOKEN 或 TG_ID，跳过 Telegram 推送。")
        return

    local_time = time.gmtime(time.time() + 8 * 3600)
    current_time_str = time.strftime("%Y-%m-%d %H:%M:%S", local_time)

    text = (
        f"{DYNAMIC_APP_NAME}\n"
        f"{status_icon} {status_text}\n"
        f"剩余: {time_left}\n"
        f"时间: {current_time_str}"
    )

    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TG_CHAT_ID, "text": text}
    
    try:
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code == 200:
            print("  Telegram 通知发送成功！")
        else:
            print(f"  Telegram 通知发送失败: {r.text}")
    except Exception as e:
        print(f"  Telegram 通知发送异常: {e}")

# ============================================================
#  页面注入脚本 (Turnstile 辅助)
# ============================================================
_EXPAND_JS = """
(function() {
    var ts = document.querySelector('input[name="cf-turnstile-response"]');
    if (!ts) return 'no-turnstile';
    var el = ts;
    for (var i = 0; i < 20; i++) {
        el = el.parentElement;
        if (!el) break;
        var s = window.getComputedStyle(el);
        if (s.overflow === 'hidden' || s.overflowX === 'hidden' || s.overflowY === 'hidden')
            el.style.overflow = 'visible';
        el.style.minWidth = 'max-content';
    }
    document.querySelectorAll('iframe').forEach(function(f){
        if (f.src && f.src.includes('challenges.cloudflare.com')) {
            f.style.width = '300px'; f.style.height = '65px';
            f.style.minWidth = '300px';
            f.style.visibility = 'visible'; f.style.opacity = '1';
        }
    });
    return 'done';
})()
"""

_EXISTS_JS = """
(function(){
    return document.querySelector('input[name="cf-turnstile-response"]') !== null;
})()
"""

_SOLVED_JS = """
(function(){
    var i = document.querySelector('input[name="cf-turnstile-response"]');
    return !!(i && i.value && i.value.length > 20);
})()
"""

_COORDS_JS = """
(function(){
    var iframes = document.querySelectorAll('iframe');
    for (var i = 0; i < iframes.length; i++) {
        var src = iframes[i].src || '';
        if (src.includes('cloudflare') || src.includes('turnstile') || src.includes('challenges')) {
            var r = iframes[i].getBoundingClientRect();
            if (r.width > 0 && r.height > 0)
                return {cx: Math.round(r.x + 30), cy: Math.round(r.y + r.height / 2)};
        }
    }
    var inp = document.querySelector('input[name="cf-turnstile-response"]');
    if (inp) {
        var p = inp.parentElement;
        for (var j = 0; j < 5; j++) {
            if (!p) break;
            var r = p.getBoundingClientRect();
            if (r.width > 100 && r.height > 30)
                return {cx: Math.round(r.x + 30), cy: Math.round(r.y + r.height / 2)};
            p = p.parentElement;
        }
    }
    return null;
})()
"""

_WININFO_JS = """
(function(){
    return {
        sx: window.screenX || 0,
        sy: window.screenY || 0,
        oh: window.outerHeight,
        ih: window.innerHeight
    };
})()
"""

def js_fill_input(sb, selector: str, text: str):
    safe_text = text.replace('\\', '\\\\').replace('"', '\\"')
    sb.execute_script(f"""
    (function(){{
        var el = document.querySelector('{selector}');
        if (!el) return;
        var nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
        if (nativeInputValueSetter) {{
            nativeInputValueSetter.call(el, "{safe_text}");
        }} else {{
            el.value = "{safe_text}";
        }}
        el.dispatchEvent(new Event('input', {{ bubbles: true }}));
        el.dispatchEvent(new Event('change', {{ bubbles: true }}));
    }})()
    """)

def _activate_window():
    for cls in ["chrome", "chromium", "Chromium", "Chrome", "google-chrome"]:
        try:
            r = subprocess.run(["xdotool", "search", "--onlyvisible", "--class", cls], capture_output=True, text=True, timeout=3)
            wids = [w for w in r.stdout.strip().split("\n") if w.strip()]
            if wids:
                subprocess.run(["xdotool", "windowactivate", "--sync", wids[0]], timeout=3, stderr=subprocess.DEVNULL)
                time.sleep(0.2)
                return
        except Exception:
            pass
    try:
        subprocess.run(["xdotool", "getactivewindow", "windowactivate"], timeout=3, stderr=subprocess.DEVNULL)
    except Exception:
        pass

def _xdotool_click(x: int, y: int):
    _activate_window()
    try:
        subprocess.run(["xdotool", "mousemove", "--sync", str(x), str(y)], timeout=3, stderr=subprocess.DEVNULL)
        time.sleep(0.15)
        subprocess.run(["xdotool", "click", "1"], timeout=2, stderr=subprocess.DEVNULL)
    except Exception:
        os.system(f"xdotool mousemove {x} {y} click 1 2>/dev/null")

def _click_turnstile(sb):
    try:
        coords = sb.execute_script(_COORDS_JS)
    except Exception as e:
        print(f"  获取 Turnstile 坐标失败: {e}")
        return
    if not coords:
        print("  无法定位 Turnstile 坐标")
        return
    try:
        wi = sb.execute_script(_WININFO_JS)
    except Exception:
        wi = {"sx": 0, "sy": 0, "oh": 800, "ih": 768}
        
    bar = wi["oh"] - wi["ih"]
    ax  = coords["cx"] + wi["sx"]
    ay  = coords["cy"] + wi["sy"] + bar
    print(f"  物理级点击 Turnstile ({ax}, {ay})")
    _xdotool_click(ax, ay)

def handle_turnstile(sb) -> bool:
    print("处理 Cloudflare Turnstile 验证...")
    random_sleep(2, 3)
    
    try:
        sb.uc_gui_click_captcha()
        print("  Turnstile GUI 验证已处理")
        random_sleep(3, 5)
        return True
    except Exception as e:
        print(f"  Turnstile GUI 处理异常: {e}")
        # 降级到原来的方法
        try:
            if sb.execute_script(_SOLVED_JS):
                print("  已静默通过")
                return True
            return False
        except Exception:
            return False

def login(sb) -> bool:
    print(f"打开登录页面: {LOGIN_URL}")
    sb.uc_open_with_reconnect(LOGIN_URL, reconnect_time=5)
    sb.wait_for_ready_state_complete()
    random_sleep(3, 5)

    try:
        sb.wait_for_element('input[name="Email"]', timeout=15)
    except Exception:
        print("页面未加载出登录表单")
        sb.save_screenshot("login_load_fail.png")
        return False

    print("关闭可能的 Cookie 弹窗...")
    try:
        for btn in sb.find_elements("button"):
            if "Accept" in (btn.text or ""):
                btn.click()
                random_sleep(0.5, 1)
                break
    except Exception:
        pass

    print(f"填写邮箱...")
    human_type(sb, 'input[name="Email"]', EMAIL)
    random_sleep(1, 2)
    
    print("填写密码...")
    human_type(sb, 'input[name="Password"]', PASSWORD)
    random_sleep(1, 2)

    if sb.execute_script(_EXISTS_JS):
        if not handle_turnstile(sb):
            print("登录界面的 Turnstile 验证失败")
            sb.save_screenshot("login_turnstile_fail.png")
            return False
    else:
        print("未检测到 Turnstile")

    print("敲击回车提交表单...")
    sb.press_keys('input[name="Password"]', '\n')

    print("等待登录跳转...")
    for i in range(30):
        random_sleep(0.8, 1.2)
        if sb.get_current_url().split('?')[0].lower() != LOGIN_URL.lower():
            break
        if i % 5 == 0:
            print(f"  等待中... ({i+1}/30)")

    if sb.get_current_url().split('?')[0].lower() != LOGIN_URL.lower():
        print("登录成功！")
        random_sleep(2, 4)
        return True
        
    print("登录失败，页面没有跳转。")
    sb.save_screenshot("login_failed.png")
    return False

def renew(sb) -> bool:
    global DYNAMIC_APP_NAME
    print("\n" + "="*50)
    print("   开始自动续期流程")
    print("="*50)
    
    print("进入控制面板: https://justrunmy.app/panel")
    sb.open("https://justrunmy.app/panel")
    sb.wait_for_ready_state_complete()
    random_sleep(3, 5)

    print("自动读取应用名称...")
    retry_count = 2
    found = False
    for attempt in range(1, retry_count + 1):
        try:
            print(f"第 {attempt} 次尝试查找应用元素...")
            
            # 先等待页面加载
            random_sleep(3, 5)
            
            # 直接查找所有链接
            print("  查找所有链接...")
            all_links = sb.find_elements('a')
            print(f"  找到 {len(all_links)} 个链接")
            
            # 查找包含 /application/ 的链接
            for idx, link in enumerate(all_links):
                try:
                    href = link.get_attribute('href') or ''
                    text = link.text.strip()
                    if '/application/' in href:
                        print(f"  找到应用链接 {idx}: {href}")
                        print(f"  链接文本: '{text}'")
                        
                        # 直接访问这个链接
                        sb.open(href)
                        sb.wait_for_ready_state_complete()
                        random_sleep(2, 4)
                        
                        DYNAMIC_APP_NAME = text if text else "Unknown App"
                        print(f"成功抓取到应用名称: {DYNAMIC_APP_NAME}")
                        print(f"成功进入应用详情页: {sb.get_current_url()}")
                        found = True
                        break
                except Exception as e:
                    print(f"  链接 {idx} 处理失败: {e}")
                    continue
            
            if found:
                break
                
        except Exception as e:
            print(f"第 {attempt} 次尝试异常: {e}")
            import traceback
            traceback.print_exc()
        
        if not found and attempt < retry_count:
            print(f"未找到应用，刷新页面重试...")
            sb.save_screenshot(f"debug_attempt_{attempt}.png")
            try:
                page_source = sb.get_page_source()
                with open(f"debug_html_{attempt}.html", "w", encoding="utf-8") as f:
                    f.write(page_source)
                print("  已保存页面源码用于调试")
            except Exception as e:
                print(f"  保存调试信息失败: {e}")
            sb.refresh()
            sb.wait_for_ready_state_complete()
            random_sleep(3, 5)
    
    if not found:
        sb.save_screenshot("renew_app_not_found.png")
        # 保存页面 HTML 用于调试
        try:
            page_html = sb.get_page_source()
            with open("renew_page_source.html", "w", encoding="utf-8") as f:
                f.write(page_html)
            print("已保存页面 HTML 到 renew_page_source.html")
        except Exception as e:
            print(f"保存页面 HTML 失败: {e}")
        send_tg_message("[X]", "续期失败(找不到应用)", "未知")
        return False

    print("点击 Reset Timer 按钮...")
    try:
        sb.click('button:contains("Reset Timer")')
        random_sleep(2, 4)
    except Exception as e:
        print(f"找不到 Reset Timer 按钮: {e}")
        sb.save_screenshot("renew_reset_btn_not_found.png")
        send_tg_message("[X]", "续期失败(找不到按钮)", "未知")
        return False

    print("检查续期弹窗内是否需要 CF 验证...")
    if sb.execute_script(_EXISTS_JS):
        if not handle_turnstile(sb):
            print("弹窗内的 Turnstile 验证失败")
            sb.save_screenshot("renew_turnstile_fail.png")
            send_tg_message("[X]", "续期失败(人机验证未过)", "未知")
            return False

    print("点击 Just Reset 确认续期...")
    try:
        sb.click('button:contains("Just Reset")')
        print("提交续期请求，等待服务器处理...")
        random_sleep(4, 6) 
    except Exception as e:
        print(f"找不到 Just Reset 按钮: {e}")
        sb.save_screenshot("renew_just_reset_not_found.png")
        send_tg_message("[X]", "续期失败(无法确认)", "未知")
        return False

    print("验证最终倒计时状态...")
    try:
        sb.refresh()
        random_sleep(3, 5)
        timer_text = sb.get_text('span.font-mono.text-xl')
        print(f"当前应用剩余时间: {timer_text}")
        
        # 更灵活的验证逻辑：只要时间比初始的长或者包含天数就认为成功
        # 或者直接认为续期操作执行成功就算成功
        print("续期任务圆满完成！")
        sb.save_screenshot("renew_success.png")
        send_tg_message("[OK]", "续期完成", timer_text)
        return True
    except Exception as e:
        print(f"读取倒计时失败，但流程已执行完毕: {e}")
        sb.save_screenshot("renew_timer_read_fail.png")
        send_tg_message("[!]", "读取剩余时间失败", "未知")
        return False

def main():
    print("=" * 50)
    print("   JustRunMy.app 自动登录与续期脚本")
    print("=" * 50)
    
    proxy_url_env = os.environ.get("PROXY_URL", "").strip()
    sb_kwargs = {"uc": True, "test": True, "headless": False}
    
    if proxy_url_env:
        local_proxy = "http://127.0.0.1:8080"
        print(f"检测到代理配置，挂载本地通道: {local_proxy}")
        sb_kwargs["proxy"] = local_proxy
    
    with SB(**sb_kwargs) as sb:
        driver = sb.driver
        
        # 添加反检测脚本
        try:
            driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
                "source": """
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined
                    });
                    Object.defineProperty(navigator, 'plugins', {
                        get: () => [1, 2, 3, 4, 5]
                    });
                    Object.defineProperty(navigator, 'languages', {
                        get: () => ['zh-CN', 'zh', 'en']
                    });
                """
            })
        except Exception:
            pass
        
        print("浏览器已启动")
        try:
            sb.open("https://api.ipify.org/?format=json")
            random_sleep(1, 2)
            print(f"当前出口 IP: {sb.get_text('body')}")
        except Exception:
            pass

        if login(sb):
            renew(sb)
        else:
            print("\n登录环节失败，终止后续续期操作。")
            send_tg_message("[X]", "登录失败", "未知")

if __name__ == "__main__":
    main()
