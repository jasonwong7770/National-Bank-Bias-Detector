'''
SIMPLY CALL THE FUNCTION overtrader(file_name, sensitivity=1.5, max_gap=2)
IT SHOULD RETURN AN ARRAY OF ANOMOLIES LIKE THIS
ex: 2025-03-02 23:54:50;2025-03-03 00:15:50
'''


from dataclasses import dataclass

@dataclass
class Timestamp:
    year: int
    month: int
    day: int
    hour: int
    minute: int
    second: int

    def to_seconds(self):
        return (
            self.year  * 365 * 24 * 3600 +
            self.month * 30  * 24 * 3600 +
            self.day   * 24  * 3600      +
            self.hour        * 3600      +
            self.minute      * 60        +
            self.second
        )

    def to_string(self):
        return (f"{self.year:04}-{self.month:02}-{self.day:02} "
                f"{self.hour:02}:{self.minute:02}:{self.second:02}")


def chunk_average(chunk):
    gaps = []
    for i in range(1, len(chunk)):
        diff = chunk[i].to_seconds() - chunk[i - 1].to_seconds()
        gaps.append(diff)

    avg_seconds = sum(gaps) / len(gaps)
    hours   = int(avg_seconds // 3600)
    minutes = int((avg_seconds % 3600) // 60)
    seconds = int(avg_seconds % 60)

    return {
        "avg_seconds": avg_seconds,
        "formatted":   f"{hours:02}:{minutes:02}:{seconds:02}"
    }


def calculate_threshold(averages, sensitivity=1.5):
    values = [r["avg_seconds"] for r in averages]
    
    # Median is robust — stays near 60s even with many anomaly chunks
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    median = (sorted_vals[n // 2] if n % 2 != 0 
              else (sorted_vals[n // 2 - 1] + sorted_vals[n // 2]) / 2)
    
    # MAD = median of absolute deviations from the median
    deviations = sorted([abs(v - median) for v in values])
    n = len(deviations)
    mad = (deviations[n // 2] if n % 2 != 0
           else (deviations[n // 2 - 1] + deviations[n // 2]) / 2)
    
    # Scale factor 1.4826 makes MAD comparable to std dev for normal distributions
    threshold = median - sensitivity * (1.4826 * mad)
    
    print(f"Median: {median:.1f}s | MAD: {mad:.1f}s | Anomaly threshold: below {threshold:.1f}s\n")
    return threshold


def fill_gaps(is_anomaly_flags, max_gap=2):
    """
    If two anomaly regions are separated by `max_gap` or fewer normal chunks,
    treat those normal chunks as part of the anomaly (bridge the gap).
    """
    filled = is_anomaly_flags[:]
    n = len(filled)

    i = 0
    while i < n:
        if filled[i]:                        # found start of an anomaly region
            # find where this anomaly ends
            j = i
            while j < n and filled[j]:
                j += 1
            # j is now the first non-anomaly after the region
            # look ahead for the next anomaly start within max_gap
            gap = 0
            k = j
            while k < n and not filled[k] and gap < max_gap:
                gap += 1
                k  += 1
            if k < n and filled[k]:          # there IS another anomaly within the gap
                for g in range(j, k):        # fill the gap chunks as anomaly
                    filled[g] = True
            i = j                            # continue scanning from end of this region
        else:
            i += 1

    return filled


def overtrader(file_name, sensitivity=1.5, max_gap=2):
    time = []

    with    open(file_name, "r") as file:
        next(file)
        for line in file:
            raw = line.split(",")[0].strip()
            if " " not in raw:
                continue

            date_part, time_part = raw.split(" ")
            year, month, day     = date_part.split("-")
            hour, minute, second = time_part.split(":")

            timestamp = Timestamp(
                year=int(year), month=int(month), day=int(day),
                hour=int(hour), minute=int(minute), second=int(second)
            )
            time.append(timestamp)

    # Split into chunks of 10
    chunks = [time[i:i + 10] for i in range(0, len(time), 10)]

    # First pass — compute all chunk averages
    averages     = []
    valid_chunks = []
    for chunk in chunks:
        if len(chunk) < 2:
            continue
        averages.append(chunk_average(chunk))
        valid_chunks.append(chunk)

    # Dynamically determine anomaly threshold
    threshold = calculate_threshold(averages, sensitivity)

    # Second pass — flag each chunk
    is_anomaly = [r["avg_seconds"] < threshold for r in averages]

    # Third pass — fill small gaps so nearby anomaly regions merge
    is_anomaly = fill_gaps(is_anomaly, max_gap=max_gap)

    # Print all chunks
    for idx, (chunk, result, anomaly) in enumerate(zip(valid_chunks, averages, is_anomaly)):
        flag = " *** ANOMALY" if anomaly else ""
        print(f"Chunk {idx + 1}: avg = {result['formatted']} ({result['avg_seconds']:.1f}s){flag}")

    # Final pass — group consecutive anomaly chunks into periods
    overtraded    = []
    anomaly_start = None
    anomaly_end   = None

    for chunk, anomaly in zip(valid_chunks, is_anomaly):
        if anomaly:
            if anomaly_start is None:
                anomaly_start = chunk[0]
            anomaly_end = chunk[-1]
        else:
            if anomaly_start is not None:
                overtraded.append(f"{anomaly_start.to_string()};{anomaly_end.to_string()}")
                anomaly_start = None
                anomaly_end   = None

    if anomaly_start is not None:
        overtraded.append(f"{anomaly_start.to_string()};{anomaly_end.to_string()}")

    print("\n--- Overtrading Periods ---")
    for period in overtraded:
        print(period)

    return overtraded