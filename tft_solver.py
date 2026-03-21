import pandas as pd
from ortools.sat.python import cp_model
def load_tft_data(
    excel_path,
    forbidden_units,
    forbidden_traits,
    max_cost
):
    df_units = pd.read_excel(excel_path, sheet_name="units")
    df_traits = pd.read_excel(excel_path, sheet_name="traits")

    # unit -> [traits]
    units = {}  # 弈子（第一列）
    unit_size = {}  # 单个弈子占据人口数（第四列）
    unit_value = {}  # 单个弈子战术费用价值（第五列）
    trait_power = {}  # 单个弈子为开启某个羁绊数提供多少人口（第六列）
    unit_front_weight = {}  # 弈子前排系数（第七列），（100-unit_front_weight）为后排系数，即前排系数+后排系数=100

    for _, row in df_units.iterrows():
        # ===== 费用限制 =====
        if max_cost is not None and int(row["cost"]) > max_cost:
            continue

        u = row["unit"]
        t = row["trait"]

        units.setdefault(u, []).append(t)
        unit_size[u] = int(row.get("pop"))
        unit_value[u] = int(row.get("unit_value"))
        trait_power[(u, t)] = int(row.get("trait_value"))
        unit_front_weight[u] = int(row.get("front_weight"))

    # trait -> sorted thresholds
    trait_thresholds = {}  # 羁绊人口挡位
    trait_weights = {}  # 羁绊开启得分
    for _, row in df_traits.iterrows():
        t = row["trait"]  # 羁绊（第一列）
        k = int(row["threshold"])  # 羁绊人口挡位（第二列）
        w = float(row["weight"])  # 羁绊开启得分（第三列）

        trait_thresholds.setdefault(t, set()).add(k)
        trait_weights[(t, k)] = w

    trait_thresholds = {
        t: sorted(list(v)) for t, v in trait_thresholds.items()
    }

    # ===== 禁用棋子（同步清理）=====
    for u in forbidden_units:
        units.pop(u, None)
        unit_size.pop(u, None)
        trait_power = {
            (uu, tt): v
            for (uu, tt), v in trait_power.items()
            if uu != u
        }

    # ===== 禁用羁绊 =====
    for t in forbidden_traits:
        trait_thresholds.pop(t, None)
        for u in units:
            units[u] = [x for x in units[u] if x != t]
        trait_power = {
            (uu, tt): v
            for (uu, tt), v in trait_power.items()
            if tt != t
        }

    # 删除没有任何羁绊的棋子
    units = {u: ts for u, ts in units.items() if ts}

    # 弈子、羁绊挡位、羁绊得分、弈子战术费用价值、弈子占据人口、为开启某个羁绊提供人口数、弈子前排系数
    return units, trait_thresholds, trait_weights, unit_value, unit_size, trait_power, unit_front_weight

def solve_tft(units, trait_thresholds, trait_weights, emblems, max_units, required_units, required_traits, unit_size, trait_power, unit_value, unit_front_weight, cost_weight, frontdev_weight):
    # 小队前排系数范围±75
    target_front = {
        3: 180,
        4: 250,
        5: 300,
        6: 375,
        7: 475,
        8: 550,
        9: 550,
        10: 600,
        11: 675
    }
    if max_units not in target_front:
        raise ValueError(
            f"不支持的人口数 max_units={max_units}，"
            f"仅支持 {list(target_front.keys())}"
        )
    # 读取对应人口时的小队前排系数
    target = target_front[max_units]

    model = cp_model.CpModel()
    # ---------- 变量 ----------
    x = {u: model.NewBoolVar(f"x[{u}]") for u in units}
    y = {
        (t, k): model.NewBoolVar(f"y[{t},{k}]")
        for t, levels in trait_thresholds.items()
        for k in levels
    }

    # ---------- 人口约束 ----------
    model.Add(
        sum(x[u] * unit_size.get(u, 1) for u in units) == max_units
    )

    # ---------- 固定弈子约束 ----------
    for u in required_units:
        if u not in x:
            raise ValueError(f"固定弈子 {u} 不存在或已被禁用")
        model.Add(x[u] == 1)

    # ---------- 羁绊激活 ----------
    for t, levels in trait_thresholds.items():
        trait_units = [u for u, ts in units.items() if t in ts]
        bonus = emblems.get(t, 0)

        for k in levels:
            model.Add(
                sum(
                    x[u] * trait_power.get((u, t), 1)
                    for u in trait_units
                ) + bonus
                >= k * y[(t, k)]
            )

        # 档位单调
        for i in range(1, len(levels)):
            model.Add(
                y[(t, levels[i])] <= y[(t, levels[i - 1])]
            )

    # ---------- 固定羁绊约束 ----------
    for t in required_traits:
        if t not in trait_thresholds:
            raise ValueError(f"固定羁绊 {t} 不存在或已被禁用")

        min_k = trait_thresholds[t][0]
        model.Add(y[(t, min_k)] == 1)

    # ---------- 前排权重总和 ----------
    FrontSum = model.NewIntVar(-5000, 5000, "FrontSum")

    model.Add(
        FrontSum ==
        sum(
            x[u] * unit_front_weight.get(u, 0)
            for u in units
        )
    )
    FrontDev = model.NewIntVar(0, 5000, "FrontDev")
    model.AddAbsEquality(FrontDev, FrontSum - target)
    # 新变量表示更新后的值
    UpdatedFrontDev = model.NewIntVar(0, 5000, "UpdatedFrontDeviation")
    # 添加约束：保证 UpdatedFrontDeviation = max(0, FrontDeviation - 50)
    model.AddMaxEquality(UpdatedFrontDev, [FrontDev - 75, 0])

    # ---------- 目标函数（严格递增） ----------
    model.Maximize(
        sum(
            trait_weights.get((t, k), 1.0) * y[(t, k)]
            for t, levels in trait_thresholds.items()
            for k in levels
        )
        +
        cost_weight * sum(
            unit_value[u] * x[u]
            for u in units
        )
        -
        frontdev_weight * UpdatedFrontDev
    )

    # ---------- 求解 ----------
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 5
    status = solver.Solve(model)

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None

    # 羁绊数额外设置一下防止出现重复情况
    active_traits = []
    for t, levels in trait_thresholds.items():
        max_k = max(
            (k for k in levels if solver.Value(y[(t, k)])),
            default=None
        )
        if max_k:
            active_traits.append(f"{t}({max_k})")

    return {
        "units": [u for u in units if solver.Value(x[u])],
        "active_traits": active_traits,
        "score": solver.ObjectiveValue()
    }