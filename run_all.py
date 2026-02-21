from overtrader     import overtrader
from loss_aversion  import loss_aversion, parse_trades
from revenge_trader import revenge_trader
from fomo_trader    import fomo_trader


def run_all(file_name: str, sensitivity: float = 1.5, max_gap: int = 2) -> dict:
    _, ot_chunk_lines, _ = overtrader(file_name, sensitivity, max_gap)
    la_results, la_chunk_lines = loss_aversion(file_name, sensitivity, max_gap)
    rt_results, rt_chunk_lines = revenge_trader(file_name, sensitivity, max_gap)
    _, ft_chunk_lines = fomo_trader(file_name, sensitivity, max_gap)
    final_chunk_lines = []
    for i in range(len(ot_chunk_lines)):
        labels = []
        x, y1 = ot_chunk_lines[i]
        labels.append(f"Chunk {x:>3}")
        if y1:
            labels.append("Overtrading    ")
        x, y2 = la_chunk_lines[i]
        if y2:
            labels.append("Loss Aversion  ")
        x, y3 = rt_chunk_lines[i]
        if y3:
            labels.append("Revenge Trading   ")
        x, y4 = ft_chunk_lines[i]
        if y4:
            labels.append("FOMO")
        if (y1, y2, y3, y4) == (False, False, False, False):
            labels.append("Calm")
        final_chunk_lines.append(labels)

    for labels in final_chunk_lines:
        print(" | ".join(labels))

def main():
    file_name = "uploads/mixed_trader.csv"
    run_all(file_name)


if __name__ == "__main__":
    main()
