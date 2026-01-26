import { Zap, Shield, Target, Activity } from 'lucide-react';

export default function ProtocolCard() {
  const scores = [
    { label: "Self Resonance", value: 0.85, icon: <Activity size={16} /> },
    { label: "World Resonance", value: 0.72, icon: <Zap size={16} /> },
    { label: "Trajectory", value: 0.94, icon: <Target size={16} /> },
    { label: "Energy Efficiency", value: 0.68, icon: <Shield size={16} /> },
  ];

  return (
    <div className="space-y-4">
      {scores.map((score) => (
        <div key={score.label} className="group">
          <div className="flex justify-between items-center mb-1">
            <div className="flex items-center gap-2 text-slate-300 text-sm">
              {score.icon}
              <span>{score.label}</span>
            </div>
            <span className="text-cyan-400 font-mono text-sm">{(score.value * 100).toFixed(0)}%</span>
          </div>
          <div className="h-2 w-full bg-slate-800 rounded-full overflow-hidden">
            <div
              className="h-full bg-gradient-to-r from-cyan-500 to-blue-500 rounded-full transition-all duration-500 ease-out group-hover:shadow-[0_0_10px_rgba(34,211,238,0.5)]"
              style={{ width: `${score.value * 100}%` }}
            />
          </div>
        </div>
      ))}

      <div className="pt-4 mt-6 border-t border-slate-800">
        <div className="flex justify-between items-center">
          <span className="text-slate-400 text-sm">Overall Alignment</span>
          <span className="text-xl font-bold text-white">A+</span>
        </div>
        <p className="text-xs text-slate-500 mt-2">
          System is highly resonant with intended functionality. Minimal drift detected.
        </p>
      </div>
    </div>
  );
}
