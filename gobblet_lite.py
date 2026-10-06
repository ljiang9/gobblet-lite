#!/usr/bin/env python3
"""gobblet-lite: 极简套娃棋 (Gobblet-like).

4x4 棋盘, 每位玩家 3 种尺寸(小/中/大), 大棋子可以盖住小棋子,
先连成 4 子一线者胜. 纯标准库, 无第三方依赖.
"""
import argparse
import random
import sys

N = 4
SIZE_NAME = {1: "小", 2: "中", 3: "大"}
PLAYER_NAME = {0: "甲", 1: "乙"}
GLYPH = {0: "●", 1: "○"}
MAX_HALF_MOVES = 400  # 防无限对局, 超过判和棋


class IllegalMove(ValueError):
    """非法走法."""


class Gobblet:
    """对局状态. board[r][c] 为棋子栈, 每个棋子为 (player, size)."""

    def __init__(self):
        self.board = [[[] for _ in range(N)] for _ in range(N)]
        # 每位玩家 3 个场外堆, 每堆 [大, 中, 小], 只能取顶部(小的先上)
        self.piles = [[[3, 2, 1] for _ in range(3)] for _ in range(2)]
        self.turn = 0
        self.winner = None  # 0 / 1 / None(未结束或和棋)
        self.draw = False
        self.half_moves = 0

    def copy(self):
        g = Gobblet.__new__(Gobblet)
        g.board = [[list(s) for s in row] for row in self.board]
        g.piles = [[list(p) for p in pl] for pl in self.piles]
        g.turn = self.turn
        g.winner = self.winner
        g.draw = self.draw
        g.half_moves = self.half_moves
        return g

    def top(self, r, c):
        s = self.board[r][c]
        return s[-1] if s else None

    @staticmethod
    def lines():
        ls = []
        for r in range(N):
            ls.append([(r, c) for c in range(N)])
        for c in range(N):
            ls.append([(r, c) for r in range(N)])
        ls.append([(i, i) for i in range(N)])
        ls.append([(i, N - 1 - i) for i in range(N)])
        return ls

    def has_line(self, player):
        for line in self.lines():
            ok = True
            for r, c in line:
                t = self.top(r, c)
                if t is None or t[0] != player:
                    ok = False
                    break
            if ok:
                return True
        return False

    @staticmethod
    def _check_bounds(r, c):
        if not (0 <= r < N and 0 <= c < N):
            raise IllegalMove(f"坐标越界: 行{r + 1}列{c + 1}")

    def legal_moves(self, player):
        """全部合法走法: ("drop", 堆号, r, c) 或 ("move", fr, fc, tr, tc)."""
        moves = []
        for pi, pile in enumerate(self.piles[player]):
            if not pile:
                continue
            s = pile[-1]
            for r in range(N):
                for c in range(N):
                    t = self.top(r, c)
                    if t is None or t[1] < s:
                        moves.append(("drop", pi, r, c))
        for fr in range(N):
            for fc in range(N):
                t = self.top(fr, fc)
                if t is None or t[0] != player:
                    continue
                s = t[1]
                for tr in range(N):
                    for tc in range(N):
                        if (tr, tc) == (fr, fc):
                            continue
                        tt = self.top(tr, tc)
                        if tt is None or tt[1] < s:
                            moves.append(("move", fr, fc, tr, tc))
        return moves

    def apply_move(self, player, move):
        """执行走法, 返回胜者(0/1) 或 None. 非法走法抛 IllegalMove."""
        if self.winner is not None or self.draw:
            raise IllegalMove("对局已结束")
        kind = move[0]
        if kind == "drop":
            _, pi, r, c = move
            self._check_bounds(r, c)
            if not (0 <= pi < 3):
                raise IllegalMove(f"堆号越界: {pi + 1}")
            pile = self.piles[player][pi]
            if not pile:
                raise IllegalMove(f"第{pi + 1}堆已空")
            s = pile[-1]
            t = self.top(r, c)
            if t is not None and t[1] >= s:
                raise IllegalMove("只能盖住更小的棋子")
            pile.pop()
            self.board[r][c].append((player, s))
        elif kind == "move":
            _, fr, fc, tr, tc = move
            self._check_bounds(fr, fc)
            self._check_bounds(tr, tc)
            if (fr, fc) == (tr, tc):
                raise IllegalMove("起点终点相同")
            src = self.board[fr][fc]
            if not src or src[-1][0] != player:
                raise IllegalMove("起点没有你的棋子")
            s = src[-1][1]
            t = self.top(tr, tc)
            if t is not None and t[1] >= s:
                raise IllegalMove("只能盖住更小的棋子")
            src.pop()
            self.board[tr][tc].append((player, s))
        else:
            raise IllegalMove(f"未知走法类型: {kind}")
        self.half_moves += 1
        self.turn = 1 - player
        # 记忆规则: 先判走子方(掀开底牌也算数), 再判对方
        if self.has_line(player):
            self.winner = player
        elif self.has_line(1 - player):
            self.winner = 1 - player
        return self.winner


# ---------------- AI ----------------

def _touches(move, squares):
    if move[0] == "drop":
        return (move[2], move[3]) in squares
    return (move[1], move[2]) in squares or (move[3], move[4]) in squares


def _covers_opp(game, player, move):
    """走法是否盖住了对方棋子."""
    if move[0] == "drop":
        t = game.top(move[2], move[3])
    else:
        t = game.top(move[3], move[4])
    return t is not None and t[0] != player


def ai_choose(game, player, rng):
    """贪心 AI: 即胜 > 拆对方即胜 > 盖子/中心启发式."""
    opp = 1 - player
    moves = game.legal_moves(player)
    if not moves:
        return None
    # 1. 有直接获胜走法就走
    for m in moves:
        g = game.copy()
        if g.apply_move(player, m) == player:
            return m
    # 2. 找对方的即胜走法, 尝试全部拆掉
    opp_winning = []
    for om in game.legal_moves(opp):
        g = game.copy()
        if g.apply_move(opp, om) == opp:
            opp_winning.append(om)
    if opp_winning:
        hot = set()
        for om in opp_winning:
            if om[0] == "drop":
                hot.add((om[2], om[3]))
            else:
                hot.add((om[1], om[2]))
                hot.add((om[3], om[4]))
        cands = [m for m in moves if _touches(m, hot)] or moves
        best, best_score = None, -1
        for m in cands:
            g = game.copy()
            g.apply_move(player, m)
            killed = 0
            for om in opp_winning:
                g2 = g.copy()
                try:
                    if g2.apply_move(opp, om) != opp:
                        killed += 1
                except IllegalMove:
                    killed += 1
            if killed > best_score:
                best, best_score = m, killed
                if killed == len(opp_winning):
                    break
        if best is not None and best_score > 0:
            return best
    # 3. 启发式: 盖对方子 > 中心 > 大子, 加随机打破平局
    def score(m):
        sc = rng.random()
        if _covers_opp(game, player, m):
            sc += 3.0
        r, c = (m[2], m[3]) if m[0] == "drop" else (m[3], m[4])
        if 1 <= r <= 2 and 1 <= c <= 2:
            sc += 0.6
        return sc

    return max(moves, key=score)


def play_auto_game(seed=None, verbose=False):
    rng = random.Random(seed)
    g = Gobblet()
    while g.winner is None and not g.draw:
        player = g.turn
        m = ai_choose(g, player, rng)
        if m is None:  # 无棋可走判负
            g.winner = 1 - player
            break
        g.apply_move(player, m)
        if verbose:
            print(f"{PLAYER_NAME[player]}: {describe_move(m)}")
            print(render(g))
        if g.half_moves >= MAX_HALF_MOVES:
            g.draw = True
    return g


def describe_move(m):
    if m[0] == "drop":
        _, pi, r, c = m
        return f"从第{pi + 1}堆落子到{coord_name(r, c)}"
    _, fr, fc, tr, tc = m
    return f"从{coord_name(fr, fc)}走到{coord_name(tr, tc)}"


def coord_name(r, c):
    return f"{chr(ord('a') + c)}{r + 1}"


def parse_coord(tok):
    tok = tok.strip().lower()
    if len(tok) != 2 or not ("a" <= tok[0] <= "d") or not ("1" <= tok[1] <= "4"):
        raise IllegalMove(f"坐标格式错误(应为 a1-d4): {tok}")
    return int(tok[1]) - 1, ord(tok[0]) - ord("a")


def render(g):
    out = ["   a   b   c   d"]
    for r in range(N):
        cells = []
        for c in range(N):
            t = g.top(r, c)
            cells.append(f"{GLYPH[t[0]]}{t[1]}" if t else "··")
        out.append(f"{r + 1} " + " ".join(f"[{x}]" for x in cells))
    piles = []
    for p in (0, 1):
        ps = []
        for i, pile in enumerate(g.piles[p]):
            inner = "·".join(SIZE_NAME[s] for s in reversed(pile)) or "空"
            ps.append(f"堆{i + 1}:{inner}")
        piles.append(f"{PLAYER_NAME[p]}场外[{'; '.join(ps)}]")
    out.append(" | ".join(piles))
    return "\n".join(out)


def play_interactive(ai_first=False):
    if not sys.stdin.isatty():
        print("交互模式需要终端; 无头演示请用 --auto", file=sys.stderr)
        return 2
    g = Gobblet()
    human = 1 if ai_first else 0
    rng = random.Random()
    print("gobblet-lite: 你是" + PLAYER_NAME[human] + f"({GLYPH[human]}), AI 是" +
          PLAYER_NAME[1 - human] + f"({GLYPH[1 - human]}), 大中小=3/2/1")
    print("命令: d <堆号1-3> <坐标> 落子; m <起点> <终点> 走子; q 退出. 例: d 1 b2 / m b2 c3")
    print(render(g))
    while g.winner is None and not g.draw:
        player = g.turn
        if player == human:
            try:
                cmd = input(f"{PLAYER_NAME[player]}> ").strip().split()
            except (EOFError, KeyboardInterrupt):
                print("\n已退出")
                return 0
            if not cmd:
                continue
            if cmd[0] == "q":
                print("已退出")
                return 0
            try:
                if cmd[0] == "d" and len(cmd) == 3:
                    pi = int(cmd[1]) - 1
                    r, c = parse_coord(cmd[2])
                    g.apply_move(player, ("drop", pi, r, c))
                elif cmd[0] == "m" and len(cmd) == 3:
                    fr, fc = parse_coord(cmd[1])
                    tr, tc = parse_coord(cmd[2])
                    g.apply_move(player, ("move", fr, fc, tr, tc))
                else:
                    print("命令格式不对, 例: d 1 b2 / m b2 c3")
                    continue
            except (IllegalMove, ValueError) as e:
                print(f"非法走法: {e}")
                continue
        else:
            m = ai_choose(g, player, rng)
            if m is None:
                g.winner = human
                break
            print(f"AI: {describe_move(m)}")
            g.apply_move(player, m)
        print(render(g))
        if g.half_moves >= MAX_HALF_MOVES:
            g.draw = True
    if g.draw:
        print("和棋")
    else:
        tag = "你赢了!" if g.winner == human else "AI 赢了"
        print(f"{PLAYER_NAME[g.winner]}({GLYPH[g.winner]})获胜, {tag}")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="gobblet-lite: 极简套娃棋")
    ap.add_argument("--auto", action="store_true", help="AI 对 AI 自动演示")
    ap.add_argument("--games", type=int, default=10, help="自动演示局数")
    ap.add_argument("--seed", type=int, default=None, help="随机种子")
    ap.add_argument("--verbose", action="store_true", help="自动演示打印每步")
    ap.add_argument("--ai-first", action="store_true", help="交互模式 AI 先手")
    args = ap.parse_args(argv)
    if args.auto:
        w = [0, 0, 0]  # 甲胜, 乙胜, 和棋
        for i in range(args.games):
            seed = None if args.seed is None else args.seed + i
            g = play_auto_game(seed=seed, verbose=args.verbose)
            if g.draw or g.winner is None:
                w[2] += 1
                res = "和棋"
            else:
                w[g.winner] += 1
                res = f"{PLAYER_NAME[g.winner]}胜"
            print(f"第{i + 1}/{args.games}局: {res}({g.half_moves}半回合)")
        print(f"总计: 甲胜{w[0]}, 乙胜{w[1]}, 和棋{w[2]}")
        return 0
    return play_interactive(ai_first=args.ai_first)


if __name__ == "__main__":
    sys.exit(main())
