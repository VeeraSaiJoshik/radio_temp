interface LiveWaveformProps {
  mode: 'user' | 'thinking' | 'ai';
}

const BAR_COUNT = 5;

const configs = {
  user: {
    color: '#ffca94',
    label: 'Listening',
    animation: 'waveUser',
    duration: [0.5, 0.7, 0.4, 0.6, 0.5],
    delay:    [0,   0.1, 0.2, 0.05, 0.15],
  },
  thinking: {
    color: '#a5b4fc',
    label: 'Thinking',
    animation: 'waveThink',
    duration: [1.2, 1.4, 1.1, 1.3, 1.2],
    delay:    [0,   0.2, 0.4, 0.1, 0.3],
  },
  ai: {
    color: '#67e8f9',
    label: 'Speaking',
    animation: 'waveAi',
    duration: [0.6, 0.5, 0.7, 0.55, 0.65],
    delay:    [0,   0.08, 0.16, 0.04, 0.12],
  },
};

export function LiveWaveform({ mode }: LiveWaveformProps) {
  const { color, label, animation, duration, delay } = configs[mode];

  return (
    <span className="app-no-drag flex items-center gap-2 whitespace-nowrap">
      {/* Bars */}
      <span className="flex items-center gap-[3px] h-[18px]">
        {Array.from({ length: BAR_COUNT }).map((_, i) => (
          <span
            key={i}
            style={{
              display: 'block',
              width: 3,
              height: 18,
              borderRadius: 2,
              backgroundColor: color,
              transformOrigin: 'bottom',
              animation: `${animation} ${duration[i]}s ease-in-out ${delay[i]}s infinite`,
            }}
          />
        ))}
      </span>

      {/* Label */}
      <span
        className="text-[11.5px] font-medium"
        style={{ color }}
      >
        {label}
      </span>
    </span>
  );
}
