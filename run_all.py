from overtrader     import overtrader
from loss_aversion  import loss_aversion, parse_trades
from revenge_trader import revenge_trader


def run_all(file_name: str, sensitivity: float = 1.5, max_gap: int = 2) -> dict:
    _, ot_chunk_lines, _ = overtrader(file_name, sensitivity, max_gap)
    la_results, la_chunk_lines = loss_aversion(file_name, sensitivity, max_gap)
    rt_results, rt_chunk_lines = revenge_trader(file_name, sensitivity, max_gap)
    final_chunk_lines = []
    for i in range(len(ot_chunk_lines)):
        labels = []
        x, y = ot_chunk_lines[i]
        labels.append(f"Chunk {x:>3}")
        if y:
            labels.append("Overtrading    ")
        x, y = la_chunk_lines[i]
        if y:
            labels.append("Loss Aversion  ")
        x, y = rt_chunk_lines[i]
        if y:
            labels.append("Revenge Trading")
        final_chunk_lines.append(labels)

    for labels in final_chunk_lines:
        print(" | ".join(labels))

def main():
    file_name = "uploads/mixed_trader.csv"
    run_all(file_name)


if __name__ == "__main__":
    main()
