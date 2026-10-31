import base64
import html
import json
import os
import re
import uuid
from pathlib import Path

import streamlit as st
from PIL import Image, ImageOps

DATA_FILE = Path(__file__).with_name("items.json")
ITEMS = "shopping_items"  # 주의: "items"는 session_state의 메서드명과 충돌하므로 사용 금지
EDITING = "editing_id"
EDIT_ERROR = "edit_error"  # (item_id, 메시지)
MAX_LEN = 50
IMAGE_DIR = Path(__file__).with_name("images")
IMG_TYPES = ["png", "jpg", "jpeg", "webp", "gif"]
MAX_IMG_MB = 5
# store_image가 만드는 파일명만 허용한다(items.json을 손으로 고쳐도 경로 조작이 안 되게)
IMG_NAME_RE = re.compile(r"[0-9a-f]{32}\.jpg")

st.set_page_config(page_title="쇼핑 리스트", page_icon="🛒", layout="centered")

CSS = """
<style>
header[data-testid="stHeader"] { display: none; }
.block-container { max-width: 640px; padding-top: 1.5rem; padding-bottom: 3rem; }
h1 { font-size: 2rem !important; padding-bottom: 0 !important; }
.subtitle { color: #6b7280; margin: .35rem 0 1.1rem; font-size: .95rem; }

/* 모바일에서도 행이 세로로 쌓이지 않고 한 줄 유지 */
div[data-testid="stHorizontalBlock"] { flex-wrap: nowrap !important; align-items: center; gap: .5rem; }
div[data-testid="stColumn"] { min-width: 0 !important; }

/* 아이템 행: 카드 */
div[data-testid="stHorizontalBlock"]:has(.item) {
  background: #fff; border: 1px solid #e5e7eb; border-radius: 14px;
  padding: .2rem .7rem; box-shadow: 0 1px 2px rgba(16,24,40,.04);
  transition: border-color .15s, box-shadow .15s;
}
div[data-testid="stHorizontalBlock"]:has(.item):hover {
  border-color: #a7f3d0; box-shadow: 0 4px 14px rgba(16,185,129,.14);
}
div[data-testid="stHorizontalBlock"]:has(.item.done) { background: #f9fafb; }

/* 이름 칸: 버튼(2.5rem)과 같은 높이로 세로 가운데 정렬.
   Streamlit 마크다운 컨테이너의 margin-bottom:-1rem 을 margin-bottom:1rem 으로 상쇄한다. */
.item { font-size: 1.05rem; line-height: 1.4; word-break: break-word;
        display: flex; align-items: center; min-height: 2.5rem; margin-bottom: 1rem; }
.item .thumb { flex: 0 0 auto; width: 40px; height: 40px; margin-right: .7rem; border-radius: 10px;
               overflow: hidden; background: #f3f4f6; display: flex; align-items: center; justify-content: center; }
.item .thumb img { width: 100%; height: 100%; object-fit: cover; display: block; }
.item .name { min-width: 0; }
.item.done { color: #9ca3af; }
.item.done .name { text-decoration: line-through; }
.item.done .thumb { opacity: .45; }

/* 체크박스 기본 여백을 없애 행 가운데에 오게 한다 */
div[data-testid="stCheckbox"] { min-height: 0 !important; padding: 0 !important; margin: 0 !important; }
div[data-testid="stCheckbox"] label { min-height: 0 !important; margin: 0 !important; align-items: center; }
div[class*="st-key-chk_"] { min-height: 0 !important; }

/* 버튼 */
div[data-testid="stButton"] button,
div[data-testid="stFormSubmitButton"] button {
  padding: .15rem .6rem; min-height: 2.5rem; border-radius: 10px; transition: background .15s, border-color .15s;
}
div[class*="st-key-edit_btn_"] button, div[class*="st-key-del_"] button {
  border: none; background: transparent; box-shadow: none;
}
div[class*="st-key-edit_btn_"] button:hover { background: #ecfdf5; }
div[class*="st-key-del_"] button:hover { background: #fef2f2; }

/* 입력창 / 알림 / 진행바 */
div[data-baseweb="input"] { border-radius: 12px; border: 1px solid #e5e7eb; background: #fff; }
div[data-baseweb="input"]:focus-within { border-color: #10b981; box-shadow: 0 0 0 3px rgba(16,185,129,.18); }
div[data-testid="stAlert"] { border-radius: 12px; }
div[data-testid="stFileUploaderDropzone"] { border-radius: 12px; background: #fff; border: 1px dashed #cbd5e1; }
div[data-testid="stProgress"] > div > div > div { height: .6rem; border-radius: 999px; background: #e5e7eb; }
div[data-testid="stProgress"] > div > div > div > div { background: #10b981; }
div[data-testid="stCaptionContainer"] { color: #6b7280; }
</style>
"""


# ---------- 저장/불러오기 (F5) ----------
def load_items() -> list[dict]:
    """items.json을 읽는다. 파일이 없거나 손상됐으면 빈 목록을 반환한다."""
    try:
        data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    items = []
    for idx, d in enumerate(data):
        if isinstance(d, dict) and isinstance(d.get("name"), str) and d["name"].strip():
            items.append(
                {
                    "id": str(d.get("id") or f"legacy-{idx}"),
                    "name": d["name"].strip(),
                    "checked": bool(d.get("checked", False)),
                    "image": d["image"]
                    if isinstance(d.get("image"), str) and IMG_NAME_RE.fullmatch(d["image"])
                    else None,
                }
            )
    return items


def save_items() -> None:
    """임시 파일에 쓴 뒤 교체해서, 읽는 쪽이 쓰다 만 파일을 보지 않게 한다."""
    tmp = DATA_FILE.with_suffix(".json.tmp")
    try:
        tmp.write_text(
            json.dumps(st.session_state[ITEMS], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(tmp, DATA_FILE)
        st.session_state["disk_ok"] = True
    except OSError:
        st.session_state["disk_ok"] = False
        st.session_state["save_error"] = True


def sync_from_disk() -> None:
    """다른 탭/기기에서 바뀐 내용을 반영하기 위해 파일에서 목록을 다시 읽는다.
    저장이 실패한 상태라면 메모리의 목록을 그대로 쓴다."""
    if ITEMS in st.session_state and not st.session_state.get("disk_ok", True):
        return
    st.session_state[ITEMS] = load_items()


def begin_action() -> None:
    """모든 변경 동작의 시작: 최신 파일 내용을 읽고 이전 경고를 지운다."""
    sync_from_disk()
    st.session_state.pop(EDIT_ERROR, None)


# ---------- 이미지 ----------
def _thumb_name(image: str) -> str:
    return image[:-4] + "_t.jpg"


def delete_image(image: str | None) -> None:
    if not image or not IMG_NAME_RE.fullmatch(image):
        return
    for fname in (image, _thumb_name(image)):
        try:
            (IMAGE_DIR / fname).unlink(missing_ok=True)
        except OSError:
            pass


def store_image(upload) -> str:
    """업로드된 사진을 검증하고 JPEG로 변환해 저장한다(원본 최대 800px + 128px 정사각 썸네일).
    문제가 있으면 사용자에게 보여줄 메시지로 ValueError를 낸다."""
    if upload.size > MAX_IMG_MB * 1024 * 1024:
        raise ValueError(f"사진은 {MAX_IMG_MB}MB 이하만 올릴 수 있어요.")
    try:
        img = ImageOps.exif_transpose(Image.open(upload))
        if img.mode in ("RGBA", "LA", "P"):
            img = img.convert("RGBA")
            bg = Image.new("RGB", img.size, "white")  # 투명 배경이 검게 나오지 않게
            bg.paste(img, mask=img.getchannel("A"))
            img = bg
        else:
            img = img.convert("RGB")
    except Exception:
        raise ValueError("이미지 파일을 읽을 수 없어요.") from None
    name = f"{uuid.uuid4().hex}.jpg"
    try:
        IMAGE_DIR.mkdir(exist_ok=True)
        full = img.copy()
        full.thumbnail((800, 800))
        full.save(IMAGE_DIR / name, "JPEG", quality=85)
        ImageOps.fit(img, (128, 128)).save(IMAGE_DIR / _thumb_name(name), "JPEG", quality=80)
    except OSError:
        delete_image(name)
        raise ValueError("사진을 저장하지 못했어요.") from None
    return name


@st.cache_data(show_spinner=False)
def thumb_uri(image: str) -> str:
    """목록에 직접 넣을 수 있도록 썸네일을 data URI로 만든다(파일명이 uuid라 캐시 가능)."""
    try:
        data = (IMAGE_DIR / _thumb_name(image)).read_bytes()
    except OSError:
        return ""
    return "data:image/jpeg;base64," + base64.b64encode(data).decode()


def init_state() -> None:
    if EDITING not in st.session_state:
        st.session_state[EDITING] = None
    sync_from_disk()
    if st.session_state[EDITING] and find_item(st.session_state[EDITING]) is None:
        st.session_state[EDITING] = None  # 다른 탭에서 삭제된 항목


# ---------- 로직 ----------
def find_item(item_id: str) -> dict | None:
    return next((i for i in st.session_state[ITEMS] if i["id"] == item_id), None)


def validate_name(name: str, exclude_id: str | None = None) -> str | None:
    """문제가 있으면 안내 메시지를, 없으면 None을 반환한다."""
    name = name.strip()
    if not name:
        return "아이템 이름을 입력해 주세요."
    if len(name) > MAX_LEN:
        return f"이름은 {MAX_LEN}자 이내로 입력해 주세요."
    key = name.casefold()
    if any(i["id"] != exclude_id and i["name"].casefold() == key for i in st.session_state[ITEMS]):
        return "이미 목록에 있는 아이템입니다."
    return None


def add_item(name: str, upload=None) -> str | None:
    """추가에 성공하면 None, 실패하면 안내 메시지를 반환한다."""
    begin_action()
    error = validate_name(name)
    if error:
        return error
    image = None
    if upload is not None:
        try:
            image = store_image(upload)
        except ValueError as e:
            return str(e)
    st.session_state[ITEMS].append(
        {"id": str(uuid.uuid4()), "name": name.strip(), "checked": False, "image": image}
    )
    save_items()
    return None


def toggle_item(item_id: str) -> None:
    begin_action()
    item = find_item(item_id)
    if item is not None:
        item["checked"] = bool(st.session_state.get(f"chk_{item_id}", False))
        save_items()


def delete_item(item_id: str) -> None:
    begin_action()
    removed = find_item(item_id)
    st.session_state[ITEMS] = [i for i in st.session_state[ITEMS] if i["id"] != item_id]
    if st.session_state[EDITING] == item_id:
        st.session_state[EDITING] = None
    save_items()
    if removed:
        delete_image(removed.get("image"))


def start_edit(item_id: str) -> None:
    begin_action()
    item = find_item(item_id)
    if item is None:
        return
    st.session_state[EDITING] = item_id  # 한 번에 한 항목만 수정
    st.session_state[f"edit_{item_id}"] = item["name"]


def cancel_edit() -> None:
    st.session_state[EDITING] = None
    st.session_state.pop(EDIT_ERROR, None)


def save_edit(item_id: str) -> None:
    begin_action()
    new_name = st.session_state.get(f"edit_{item_id}", "")
    error = validate_name(new_name, exclude_id=item_id)
    upload = st.session_state.get(f"img_new_{item_id}")
    remove = bool(st.session_state.get(f"img_rm_{item_id}", False))
    new_image = None
    if not error and upload is not None:
        try:
            new_image = store_image(upload)
        except ValueError as e:
            error = str(e)
    if error:
        st.session_state[EDIT_ERROR] = (item_id, error)  # 수정 모드는 유지
        return
    item = find_item(item_id)
    if item is None:  # 다른 탭에서 삭제된 항목
        delete_image(new_image)
    else:
        old_image = item.get("image")
        item["name"] = new_name.strip()
        if new_image:
            item["image"] = new_image
        elif remove:
            item["image"] = None
        save_items()
        if (new_image or remove) and old_image:
            delete_image(old_image)
    cancel_edit()


def clear_completed() -> None:
    begin_action()
    removed = [i for i in st.session_state[ITEMS] if i["checked"]]
    st.session_state[ITEMS] = [i for i in st.session_state[ITEMS] if not i["checked"]]
    if st.session_state[EDITING] and find_item(st.session_state[EDITING]) is None:
        st.session_state[EDITING] = None
    save_items()
    for i in removed:
        delete_image(i.get("image"))


# ---------- 화면 ----------
def render_add_form() -> None:
    with st.form("add_form", clear_on_submit=True, border=False):
        c_in, c_btn = st.columns([5, 1.3])
        name = c_in.text_input(
            "아이템",
            placeholder="추가할 아이템 (예: 우유)",
            max_chars=MAX_LEN,
            label_visibility="collapsed",
        )
        submitted = c_btn.form_submit_button(
            "추가", help="추가", type="primary", use_container_width=True
        )
        with st.expander("📷 사진 첨부 (선택)"):
            upload = st.file_uploader(
                "사진 (5MB 이하)", type=IMG_TYPES, key="add_img", label_visibility="collapsed"
            )
    if submitted:
        error = add_item(name, upload)
        if error:
            st.warning(error)


def render_row(item: dict) -> None:
    item_id = item["id"]
    if st.session_state[EDITING] == item_id:
        # 폼으로 감싸서 입력창에서 Enter를 누르면 저장(첫 번째 제출 버튼)된다.
        with st.form(f"editform_{item_id}", border=False):
            c_text, c_save, c_cancel = st.columns([12, 1.6, 1.6])
            c_text.text_input(
                "이름 수정",
                key=f"edit_{item_id}",
                max_chars=MAX_LEN,
                label_visibility="collapsed",
            )
            c_save.form_submit_button(
                "💾", key=f"save_{item_id}", help="저장", on_click=save_edit, args=(item_id,)
            )
            c_cancel.form_submit_button(
                "✖️", key=f"cancel_{item_id}", help="취소", on_click=cancel_edit
            )
            current = item.get("image")
            if current and (IMAGE_DIR / current).exists():
                st.image(str(IMAGE_DIR / current), width=160)
            st.file_uploader(
                "📷 사진 변경 (선택, 5MB 이하)", type=IMG_TYPES, key=f"img_new_{item_id}"
            )
            if current:
                st.checkbox("현재 사진 삭제", key=f"img_rm_{item_id}")
        error = st.session_state.get(EDIT_ERROR)
        if error and error[0] == item_id:
            st.warning(error[1])
        return

    # 다른 탭에서 바뀐 체크 상태가 위젯에 반영되도록 렌더 전에 key 값을 맞춘다.
    st.session_state[f"chk_{item_id}"] = item["checked"]
    c_chk, c_name, c_edit, c_del = st.columns([1, 12, 1.6, 1.6])
    c_chk.checkbox(
        f"완료: {item['name']}",
        key=f"chk_{item_id}",
        on_change=toggle_item,
        args=(item_id,),
        label_visibility="collapsed",
    )
    css_class = "item done" if item["checked"] else "item"
    uri = thumb_uri(item["image"]) if item.get("image") else ""
    thumb = (
        f'<span class="thumb"><img src="{uri}" alt=""></span>'
        if uri
        else '<span class="thumb">🛍️</span>'
    )
    c_name.markdown(
        f'<div class="{css_class}">{thumb}<span class="name">{html.escape(item["name"])}</span></div>',
        unsafe_allow_html=True,
    )
    c_edit.button("✏️", key=f"edit_btn_{item_id}", help="수정", on_click=start_edit, args=(item_id,))
    c_del.button("🗑️", key=f"del_{item_id}", help="삭제", on_click=delete_item, args=(item_id,))


def render_items() -> None:
    items = st.session_state[ITEMS]
    if not items:
        st.info("🧺 장바구니가 비어 있어요. 아이템을 추가해 보세요.")
        return
    for item in items:
        render_row(item)


def render_summary() -> None:
    items = st.session_state[ITEMS]
    done = sum(1 for i in items if i["checked"])
    st.caption(f"전체 {len(items)}개 · 남은 {len(items) - done}개 · 완료 {done}개")
    if done:
        st.button("완료 항목 삭제", on_click=clear_completed)


def render_progress(slot) -> None:
    items = st.session_state[ITEMS]
    if items:
        done = sum(1 for i in items if i["checked"])
        slot.progress(done / len(items), text=f"{done}/{len(items)} 완료")


def main() -> None:
    st.markdown(CSS, unsafe_allow_html=True)
    st.title("🛒 쇼핑 리스트")
    st.markdown('<div class="subtitle">오늘 살 것을 담아 보세요</div>', unsafe_allow_html=True)
    init_state()
    progress_slot = st.empty()  # 상단 자리만 잡고, 추가/삭제 처리 후 최신 값으로 채운다
    render_add_form()
    render_progress(progress_slot)
    render_items()
    render_summary()
    if st.session_state.pop("save_error", False):
        st.error("목록을 파일에 저장하지 못했습니다.")


main()
