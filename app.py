import streamlit as st
import pandas as pd
from io import BytesIO
import tempfile
import os
from tft_solver import load_tft_data, solve_tft   # 我的两个函数

st.set_page_config(page_title="TFT 阵容优化器", layout="wide")
st.title("☁️ 云顶之弈 Super大瑞兹阵容优化器")

# ── 侧边栏输入 ────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ 对局设置")

    # Excel 输入：支持上传 + 本地路径
    st.subheader("数据来源")
    uploaded_file = st.file_uploader("上传 ChessInfo.xlsx（推荐）", type=["xlsx"])
    excel_path_input = st.text_input(
        "或填写本地 Excel 路径（没上传时使用）",
        value="ChessInfo.xlsx",
        placeholder="例如：D:/云顶小巧思/ChessInfo.xlsx"
    )

    # === 目标人口和最高弈子费用 ===
    col1, col2 = st.columns(2)
    with col1:
        max_units = st.number_input("目标人口", min_value=3, max_value=12, value=8, step=1)
    with col2:
        max_cost = st.number_input("最高弈子费用", min_value=1, max_value=7, value=4, step=1)

    # === 禁用 ===
    st.subheader("禁用")
    forbidden_units = st.text_input("禁用弈子（英文逗号分隔）", "加里奥,永恩,奥利瑞安索尔,维迦")
    forbidden_units = [u.strip() for u in forbidden_units.split(",") if u.strip()]

    forbidden_traits = st.text_input("禁用羁绊（英文逗号分隔）", "暗影岛")
    forbidden_traits = [t.strip() for t in forbidden_traits.split(",") if t.strip()]

    # === 转职 ===
    st.subheader("你拥有的转职")
    emblem_input = st.text_area(
        "(格式：羁绊名:数量 英文逗号分隔)",
        value="祖安:1,皮尔特沃夫:1,约德尔人:1,诺克萨斯:1",
        height=150,
        help="例如：祖安:3,皮尔特沃夫:2"
    )

    # === 强制项 ===
    st.subheader("强制上阵")
    required_units_input = st.text_input(
        "强制上阵弈子 (英文逗号分隔)",
        value="提莫,德莱文",
        help="例如：提莫,德莱文"
    )
    required_units = [u.strip() for u in required_units_input.split(",") if u.strip()]

    required_traits_input = st.text_input(
        "强制羁绊（格式：羁绊:档位 英文逗号分隔）",
        value="祖安:3,皮尔特沃夫:2",
        help="例如：祖安:3,皮尔特沃夫:2"
    )

    # 权重
    st.subheader("优化偏好")
    cost_weight = st.slider("弈子价值权重", 0.0, 2.0, 0.3, 0.1)
    frontdev_weight = st.slider("前后排惩罚权重", 0.0, 2.0, 0.1, 0.05)

# ── 计算按钮 ────────────────────────────────────────
if st.button("🔥 开始生成 ", type="primary", use_container_width=True):
    # 决定 Excel 来源
    if uploaded_file is not None:
        excel_input = uploaded_file
        source_type = "upload"
    elif excel_path_input.strip():
        excel_input = excel_path_input.strip()
        source_type = "local"
    else:
        st.error("请上传 Excel 文件 或 填写正确的本地路径")
        st.stop()

    try:
        # 处理成路径字符串
        if source_type == "local":
            excel_path = excel_input
        else:
            # 上传文件 → 临时保存
            with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
                tmp.write(excel_input.getvalue())
                tmp.flush()
                excel_path = tmp.name

        # 解析转职（支持叠加）
        emblems = {}
        for line in emblem_input.strip().split(","):
            if ":" in line:
                t, num = line.split(":", 1)
                emblems[t.strip()] = int(num.strip())

        # 解析强制羁绊
        required_traits = {}
        if required_traits_input.strip():
            for item in required_traits_input.split(","):
                if ":" in item:
                    t, k = item.split(":", 1)
                    required_traits[t.strip()] = int(k.strip())

        with st.spinner("正在加载数据并求解..."):
            units, trait_thresholds, trait_weights, unit_value, unit_size, trait_power, unit_front_weight = load_tft_data(
                excel_path, forbidden_units, forbidden_traits, max_cost
            )

            result = solve_tft(
                units, trait_thresholds, trait_weights, emblems,
                max_units, required_units, required_traits,   # ← 这里已传入强制羁绊
                unit_size, trait_power, unit_value, unit_front_weight,
                cost_weight, frontdev_weight
            )

        if result is None:
            st.error("❌ 无解！建议：减少禁用、增加人口、或放宽费用限制")
        else:
            st.success(f"✅ 最优阵容！总分：{result['score']:.2f}")

            col1, col2 = st.columns([3, 2])
            with col1:
                st.subheader("上场弈子")
                st.dataframe(pd.DataFrame({"弈子": sorted(result["units"])}), use_container_width=True, hide_index=True)
            with col2:
                st.subheader("激活羁绊")
                for trait in sorted(result["active_traits"]):
                    st.markdown(f"**{trait}**")

    except Exception as e:
        st.error(f"出错：{str(e)}\n请检查 Excel 路径、输入格式是否正确")

st.caption("2026.3.21 于太阳纸业")