document.addEventListener("DOMContentLoaded", () => {
    // 處理時間軸的預設滾動位置
    const container = document.getElementById('timeline-container');
    if (container) {
        container.scrollLeft = 150;
    }

    // 初始化所有可打字篩選的下拉 (combobox)
    document.querySelectorAll('[data-combobox]').forEach(initCombobox);
    setupComboboxFormValidation();
});

// =============================================
// Searchable combobox (打字模糊篩選 + 只能選現有項目)
//
// Expected markup:
//   <div data-combobox data-required>
//     <input type="hidden" name="field" value="...">      ← 實際送出的值
//     <input type="text" class="combo-input" ...>          ← 顯示/搜尋用
//     <ul class="combo-list hidden">
//       <li class="combo-option" data-value="ID" data-label="顯示名稱">顯示名稱 ...</li>
//     </ul>
//   </div>
// =============================================
function initCombobox(root) {
    const hidden = root.querySelector('input[type="hidden"]');
    const input = root.querySelector('.combo-input');
    const list = root.querySelector('.combo-list');
    if (!hidden || !input || !list) return;

    const options = Array.from(list.querySelectorAll('.combo-option'));
    let activeIdx = -1;

    function labelFor(value) {
        const opt = options.find(o => o.dataset.value === value);
        return opt ? opt.dataset.label : '';
    }

    // 確保初始顯示文字與已選值一致
    if (hidden.value) {
        const lbl = labelFor(hidden.value);
        if (lbl) input.value = lbl;
    }

    function openList() {
        list.classList.remove('hidden');
    }
    function closeList() {
        list.classList.add('hidden');
        activeIdx = -1;
        options.forEach(o => o.classList.remove('combo-active'));
    }

    function filter() {
        const q = input.value.trim().toLowerCase();
        let firstVisible = -1;
        options.forEach((o, i) => {
            const hay = o.dataset.label.toLowerCase();
            const match = q === '' || hay.includes(q);
            o.style.display = match ? '' : 'none';
            if (match && firstVisible === -1) firstVisible = i;
        });
        activeIdx = firstVisible;
        highlight();
    }

    function highlight() {
        options.forEach((o, i) => {
            o.classList.toggle('combo-active', i === activeIdx);
        });
        const cur = options[activeIdx];
        if (cur && cur.style.display !== 'none') {
            cur.scrollIntoView({ block: 'nearest' });
        }
    }

    function selectOption(opt) {
        if (!opt) return;
        hidden.value = opt.dataset.value;
        input.value = opt.dataset.label;
        closeList();
        hidden.dispatchEvent(new Event('change', { bubbles: true }));
    }

    // 失焦時：若輸入文字未對應任何現有項目，還原為上次選取（或清空）
    function reconcile() {
        const exact = options.find(o => o.dataset.label.toLowerCase() === input.value.trim().toLowerCase());
        if (exact) {
            selectOption(exact);
        } else if (hidden.value) {
            input.value = labelFor(hidden.value); // 還原成已選的
        } else {
            input.value = '';
        }
    }

    input.addEventListener('focus', () => { filter(); openList(); });
    input.addEventListener('input', () => { hidden.value = ''; filter(); openList(); });

    input.addEventListener('keydown', (e) => {
        const visible = options.filter(o => o.style.display !== 'none');
        if (e.key === 'ArrowDown') {
            e.preventDefault();
            openList();
            if (visible.length) {
                const curPos = visible.indexOf(options[activeIdx]);
                const np = visible[Math.min(visible.length - 1, curPos + 1)] || visible[0];
                activeIdx = options.indexOf(np);
                highlight();
            }
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            const curPos = visible.indexOf(options[activeIdx]);
            const pp = visible[Math.max(0, curPos - 1)] || visible[0];
            activeIdx = options.indexOf(pp);
            highlight();
        } else if (e.key === 'Enter') {
            if (!list.classList.contains('hidden')) {
                e.preventDefault();
                if (options[activeIdx] && options[activeIdx].style.display !== 'none') {
                    selectOption(options[activeIdx]);
                }
            }
        } else if (e.key === 'Escape') {
            closeList();
        }
    });

    options.forEach(o => {
        // mousedown 先於 blur，避免點選前就被 reconcile 清掉
        o.addEventListener('mousedown', (e) => { e.preventDefault(); selectOption(o); });
    });

    input.addEventListener('blur', () => { setTimeout(() => { closeList(); reconcile(); }, 120); });
}

function setupComboboxFormValidation() {
    document.querySelectorAll('form').forEach(form => {
        if (!form.querySelector('[data-combobox][data-required]')) return;
        form.addEventListener('submit', (e) => {
            let bad = null;
            form.querySelectorAll('[data-combobox][data-required]').forEach(root => {
                const hidden = root.querySelector('input[type="hidden"]');
                if (hidden && !hidden.value && !bad) bad = root;
            });
            if (bad) {
                e.preventDefault();
                const input = bad.querySelector('.combo-input');
                if (input) { input.focus(); }
                alert('請從清單中選擇有效的項目');
            }
        });
    });
}

// =============================================
// Theme toggle (light -> dark -> system). Initial class is applied by the
// inline script in base.html <head>; this only wires the header button.
// =============================================
(function () {
    const MODES = ['light', 'dark', 'system'];
    const ICONS = { light: 'light_mode', dark: 'dark_mode', system: 'brightness_auto' };
    const LABELS = { light: '淺色', dark: '深色', system: '跟隨系統' };
    const mq = window.matchMedia('(prefers-color-scheme: dark)');

    function currentMode() {
        const m = document.documentElement.getAttribute('data-theme-mode');
        return MODES.includes(m) ? m : 'dark';
    }
    function apply(mode) {
        const dark = mode === 'dark' || (mode === 'system' && mq.matches);
        document.documentElement.classList.toggle('dark', dark);
        document.documentElement.setAttribute('data-theme-mode', mode);
        document.querySelectorAll('[data-theme-toggle]').forEach(btn => {
            const icon = btn.querySelector('.material-symbols-outlined');
            if (icon && icon.textContent !== ICONS[mode]) {
                icon.textContent = ICONS[mode];
                icon.classList.remove('icon-swap');
                void icon.offsetWidth; // restart the animation
                icon.classList.add('icon-swap');
            }
            btn.title = '外觀：' + LABELS[mode] + '（點擊切換）';
            btn.setAttribute('aria-label', '外觀：' + LABELS[mode] + '，點擊切換');
        });
    }
    document.addEventListener('DOMContentLoaded', () => {
        apply(currentMode());
        document.querySelectorAll('[data-theme-toggle]').forEach(btn => {
            btn.addEventListener('click', () => {
                const next = MODES[(MODES.indexOf(currentMode()) + 1) % MODES.length];
                try { localStorage.setItem('theme', next); } catch (e) { }
                apply(next);
            });
        });
    });
    const onSystemChange = () => { if (currentMode() === 'system') apply('system'); };
    if (mq.addEventListener) mq.addEventListener('change', onSystemChange);
})();

// =============================================
// Flash messages: success auto-dismisses, errors stay until closed.
// =============================================
document.addEventListener('DOMContentLoaded', () => {
    function dismiss(el) {
        el.style.opacity = '0';
        el.style.transform = 'translateY(-6px)';
        setTimeout(() => {
            const parent = el.parentElement;
            el.remove();
            if (parent && parent.id === 'flash-container' && !parent.children.length) parent.remove();
        }, 500);
    }
    document.querySelectorAll('[data-flash-close]').forEach(btn => {
        btn.addEventListener('click', () => dismiss(btn.closest('.flash-msg')));
    });
    document.querySelectorAll('.flash-msg[data-autodismiss]').forEach(el => {
        setTimeout(() => dismiss(el), 4000);
    });
});

// =============================================
// Shared confirm dialog (<dialog id="confirm-dialog"> from _confirm.html)
//   confirmDialog(message, {title, confirmText}) -> Promise<boolean>
//   <form data-confirm="..."> / <a data-confirm="..."> are handled automatically.
// Esc, backdrop click and the 取消 button all resolve false; focus starts on 取消.
// =============================================
function confirmDialog(message, opts) {
    opts = opts || {};
    return new Promise(resolve => {
        const dlg = document.getElementById('confirm-dialog');
        if (!dlg || typeof dlg.showModal !== 'function' || dlg.open) {
            resolve(false); // fail closed: never delete without an explicit OK
            return;
        }
        dlg.querySelector('#confirm-title').textContent = opts.title || '確認刪除';
        dlg.querySelector('#confirm-message').textContent = message || '';
        dlg.querySelector('#confirm-ok').textContent = opts.confirmText || '確定刪除';
        dlg.returnValue = 'cancel';

        const onClick = (e) => { if (e.target === dlg) dlg.close('cancel'); }; // backdrop click
        dlg.addEventListener('click', onClick);
        dlg.addEventListener('close', () => {
            dlg.removeEventListener('click', onClick);
            resolve(dlg.returnValue === 'ok');
        }, { once: true });

        dlg.showModal();
        dlg.querySelector('#confirm-cancel').focus();
    });
}
window.confirmDialog = confirmDialog;

document.addEventListener('submit', (e) => {
    const form = e.target;
    if (!(form instanceof HTMLFormElement) || !form.dataset.confirm) return;
    if (form.dataset.confirmed === '1') { delete form.dataset.confirmed; return; }
    e.preventDefault();
    const submitter = e.submitter;
    confirmDialog(form.dataset.confirm).then(ok => {
        if (!ok) return;
        form.dataset.confirmed = '1';
        if (form.requestSubmit) form.requestSubmit(submitter || undefined); else form.submit();
    });
}, true);

// rows: array of arrays. Quotes every cell; a leading = + - @ tab CR gets a ' prefix (CSV formula injection).
function downloadCsv(filename, rows) {
    const q = v => '"' + String(v).replace(/^[=+\-@\t\r]/, "'$&").replace(/"/g, '""') + '"';
    const blob = new Blob(['﻿' + rows.map(r => r.map(q).join(',')).join('\r\n')], { type: 'text/csv;charset=utf-8' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = filename;
    a.click();
    URL.revokeObjectURL(a.href);
}
window.downloadCsv = downloadCsv;

// Substring-filter list rows by data-search; extraTest(row) may veto. Toggles #<noMatchId> when nothing shows.
function filterRows(input, rowSelector, noMatchId, extraTest) {
    const q = input.value.trim().toLowerCase();
    let shown = 0;
    document.querySelectorAll(rowSelector).forEach(row => {
        const ok = row.dataset.search.includes(q) && (!extraTest || extraTest(row));
        row.style.display = ok ? '' : 'none';
        if (ok) shown++;
    });
    document.getElementById(noMatchId).classList.toggle('hidden', shown > 0 || !document.querySelector(rowSelector));
}
window.filterRows = filterRows;

// Hours total + character counter, driven by data attributes (add/edit task forms).
document.addEventListener('DOMContentLoaded', () => {
    const total = document.querySelector('[data-hours-total]');
    if (!total) return;
    const f = total.closest('form'), inputs = f.querySelectorAll('[data-hours]');
    const upd = () => {
        let t = 0;
        inputs.forEach(i => { t += parseFloat(i.value) || 0; });
        total.textContent = +t.toFixed(2);
        f.querySelectorAll('[data-char-count]').forEach(c => {
            c.textContent = document.getElementById(c.dataset.charCount).value.length;
        });
    };
    f.addEventListener('input', upd);
    upd();
});

// =============================================
// Motion helpers: shake invalid fields, sliding tab indicator.
// =============================================
document.addEventListener('invalid', (e) => {
    const el = e.target;
    el.classList.remove('shake');
    void el.offsetWidth; // restart the animation
    el.classList.add('shake');
    el.addEventListener('animationend', () => el.classList.remove('shake'), { once: true });
}, true);

// <div data-tabs> with children marked aria-selected="true" when active.
document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('[data-tabs]').forEach(bar => {
        const bar_ind = document.createElement('span');
        bar_ind.className = 'tab-indicator';
        bar_ind.setAttribute('aria-hidden', 'true');
        bar.appendChild(bar_ind);
        const place = () => {
            const active = bar.querySelector('[aria-selected="true"]');
            bar_ind.style.opacity = active ? '1' : '0';
            if (!active) return;
            bar_ind.style.width = active.offsetWidth + 'px';
            bar_ind.style.transform = `translateX(${active.offsetLeft}px)`;
        };
        place();
        new MutationObserver(place).observe(bar, { attributes: true, subtree: true, attributeFilter: ['aria-selected'] });
        window.addEventListener('resize', place);
    });
});

// Mobile hamburger (<details> in _header.html): close when tapping outside it
document.addEventListener('click', (e) => {
    document.querySelectorAll('header details[open]').forEach(d => { if (!d.contains(e.target)) d.open = false; });
});
