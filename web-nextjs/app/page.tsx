"use client";

import { useState, useEffect, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";

const PAPERS = [
  { id: "college_ruled", label: "College Ruled", desc: "Classic notebook", color: "#f8f6f2", accent: "#b4d2e6" },
  { id: "blank", label: "Blank Paper", desc: "Clean white", color: "#faf8f5", accent: "#e8e6e3" },
  { id: "graph", label: "Graph Paper", desc: "5mm grid", color: "#ffffff", accent: "#c8d0d8" },
  { id: "legal_pad", label: "Legal Pad", desc: "Yellow ruled", color: "#fffccd", accent: "#8caac8" },
  { id: "dot_grid", label: "Dot Grid", desc: "Bullet journal", color: "#ffffff", accent: "#d0d0d0" },
  { id: "sticky_note", label: "Sticky Note", desc: "3×3 yellow", color: "#fff9a8", accent: "#e8d840" },
];

const INKS = [
  { id: "black", label: "Black", hex: "#0a0a0a" },
  { id: "blue", label: "Blue", hex: "#0f196e" },
  { id: "dark_blue", label: "Navy", hex: "#050f50" },
  { id: "green", label: "Green", hex: "#0a3c23" },
  { id: "red", label: "Red", hex: "#820f0f" },
  { id: "pencil", label: "Pencil", hex: "#505050" },
];

const EFFECTS = [
  { id: "scan", label: "Scanned", desc: "Flatbed scanner look" },
  { id: "phone", label: "Phone Photo", desc: "Camera capture feel" },
  { id: "clean", label: "Clean Render", desc: "No artifacts" },
];

// Fake preview lines that simulate handwriting layout
function HandwritingPreview({ text, ink, paper, isGenerating }: any) {
  const words = text.split(" ").filter(Boolean);
  const lines = [];
  let currentLine: string[] = [];
  let lineWidth = 0;

  words.forEach((word: string) => {
    const wordWidth = word.length * 11;
    if (lineWidth + wordWidth > 380 && currentLine.length > 0) {
      lines.push(currentLine);
      currentLine = [word];
      lineWidth = wordWidth;
    } else {
      currentLine.push(word);
      lineWidth += wordWidth + 14;
    }
  });
  if (currentLine.length > 0) lines.push(currentLine);

  return (
    <div
      className="relative overflow-hidden rounded-sm"
      style={{
        background: paper?.color || "#f8f6f2",
        minHeight: 280,
        fontFamily: "var(--font-caveat)",
      }}
    >
      {/* Paper lines for ruled types */}
      {(paper?.id === "college_ruled" || paper?.id === "legal_pad") && (
        <svg className="absolute inset-0 w-full h-full pointer-events-none" preserveAspectRatio="none">
          {Array.from({ length: 10 }, (_, i) => (
            <line
              key={i}
              x1="0" y1={42 + i * 28} x2="100%" y2={42 + i * 28}
              stroke={paper?.accent || "#b4d2e6"}
              strokeWidth="0.7"
              opacity="0.6"
            />
          ))}
          {paper?.id === "college_ruled" && (
            <line x1="52" y1="0" x2="52" y2="100%" stroke="#dcaaaa" strokeWidth="0.7" opacity="0.5" />
          )}
        </svg>
      )}

      {/* Dot grid */}
      {paper?.id === "dot_grid" && (
        <svg className="absolute inset-0 w-full h-full pointer-events-none">
          {Array.from({ length: 12 }, (_, row) =>
            Array.from({ length: 18 }, (_, col) => (
              <circle key={`${row}-${col}`} cx={20 + col * 24} cy={20 + row * 24} r="0.8" fill="#c0c0c0" opacity="0.5" />
            ))
          )}
        </svg>
      )}

      {/* Graph grid */}
      {paper?.id === "graph" && (
        <svg className="absolute inset-0 w-full h-full pointer-events-none">
          {Array.from({ length: 20 }, (_, i) => (
            <g key={i}>
              <line x1={i * 24} y1="0" x2={i * 24} y2="100%" stroke="#d0d8e0" strokeWidth="0.4" />
              <line x1="0" y1={i * 24} x2="100%" y2={i * 24} stroke="#d0d8e0" strokeWidth="0.4" />
            </g>
          ))}
        </svg>
      )}

      {/* Handwriting text */}
      <div className="relative z-10 p-6 pt-8" style={{ paddingLeft: paper?.id === "college_ruled" ? 62 : 24 }}>
        <AnimatePresence mode="wait">
          {isGenerating ? (
            <motion.div
              key="generating"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="flex items-center justify-center h-48"
            >
              <div className="flex gap-1.5">
                {[0, 1, 2].map((i) => (
                  <motion.div
                    key={i}
                    animate={{ y: [-4, 4, -4] }}
                    transition={{ duration: 0.6, repeat: Infinity, delay: i * 0.15 }}
                    className="w-2 h-2 rounded-full"
                    style={{ background: ink?.hex || "#0a0a0a" }}
                  />
                ))}
              </div>
            </motion.div>
          ) : (
            <motion.div key="text" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.3 }}>
              {lines.map((line: string[], lineIdx: number) => (
                <motion.div
                  key={lineIdx}
                  initial={{ opacity: 0, x: -8 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: lineIdx * 0.08, duration: 0.3 }}
                  className="leading-7 text-lg tracking-wide"
                  style={{
                    color: ink?.hex || "#0a0a0a",
                    transform: `rotate(${Math.sin(lineIdx * 1.3) * 0.3}deg) translateY(${Math.sin(lineIdx * 0.7) * 1.2}px)`,
                    opacity: text ? 0.88 : 0.25,
                  }}
                >
                  {line.join(" ") || (lineIdx === 0 ? "Start typing to preview..." : "")}
                </motion.div>
              ))}
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}

export default function InkClone() {
  const [text, setText] = useState("The quick brown fox jumps over the lazy dog");
  const [paper, setPaper] = useState(PAPERS[0]);
  const [ink, setInk] = useState(INKS[0]);
  const [effect, setEffect] = useState(EFFECTS[0]);
  const [neatness, setNeatness] = useState(0.7);
  const [isGenerating, setIsGenerating] = useState(false);
  const [generatedImage, setGeneratedImage] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState("paper");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleGenerate = async () => {
    setIsGenerating(true);
    setGeneratedImage(null);
    try {
      const res = await fetch("http://localhost:8000/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text,
          paper: paper.id,
          ink: ink.id,
          artifact: effect.id,
          neatness,
        }),
      });
      if (res.ok) {
        const data = await res.json();
        if (data.success && data.image) {
          setGeneratedImage(data.image);
        }
      }
    } catch (e) {
      console.error("Generation failed:", e);
    }
    setIsGenerating(false);
  };

  return (
    <div
      className="min-h-screen"
      style={{
        background: "#0c0c0f",
        color: "#e8e6e3",
        fontFamily: "var(--font-dm-sans)",
      }}
    >
      {/* Subtle grain overlay */}
      <div
        className="fixed inset-0 pointer-events-none z-50 opacity-[0.03]"
        style={{
          backgroundImage: `url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noise)'/%3E%3C/svg%3E")`,
          backgroundRepeat: "repeat",
        }}
      />

      <div className="relative z-10 max-w-5xl mx-auto px-6 py-12">
        {/* Header */}
        <motion.header
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6 }}
          className="mb-16"
        >
          <div className="flex items-center gap-3 mb-3">
            <div className="w-8 h-8 rounded-md flex items-center justify-center" style={{ background: "#1a1a2e" }}>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#7c6fe0" strokeWidth="2.5" strokeLinecap="round">
                <path d="M17 3a2.83 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z" />
              </svg>
            </div>
            <h1 className="text-xl font-semibold tracking-tight" style={{ color: "#f0eee8" }}>
              InkClone
            </h1>
            <span
              className="text-[10px] font-medium px-2 py-0.5 rounded-full ml-1"
              style={{ background: "#1a1a2e", color: "#7c6fe0" }}
            >
              BETA
            </span>
          </div>
          <p className="text-sm" style={{ color: "#6b6970" }}>
            Your handwriting, digitally replicated. Type anything and get a realistic handwritten document.
          </p>
        </motion.header>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          {/* Left Column — Controls */}
          <motion.div
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.5, delay: 0.1 }}
            className="space-y-6"
          >
            {/* Text Input */}
            <div>
              <label className="text-xs font-medium mb-2 block" style={{ color: "#8a8890", letterSpacing: "0.06em" }}>
                YOUR TEXT
              </label>
              <div className="relative">
                <textarea
                  ref={textareaRef}
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                  rows={4}
                  className="w-full px-4 py-3 rounded-lg text-sm resize-none focus:outline-none transition-all duration-200"
                  style={{
                    background: "#141418",
                    border: "1px solid #2a2a30",
                    color: "#d8d6d0",
                    fontFamily: "var(--font-dm-sans)",
                  }}
                  onFocus={(e) => ((e.target as HTMLTextAreaElement).style.borderColor = "#7c6fe0")}
                  onBlur={(e) => ((e.target as HTMLTextAreaElement).style.borderColor = "#2a2a30")}
                  placeholder="Type what you want handwritten..."
                />
                <span className="absolute bottom-2 right-3 text-[10px]" style={{ color: "#4a4850" }}>
                  {text.length} chars
                </span>
              </div>
            </div>

            {/* Tab Navigation */}
            <div className="flex gap-1 p-1 rounded-lg" style={{ background: "#141418" }}>
              {["paper", "ink", "effects"].map((tab) => (
                <button
                  key={tab}
                  onClick={() => setActiveTab(tab)}
                  className="flex-1 py-2 px-3 rounded-md text-xs font-medium transition-all duration-200"
                  style={{
                    background: activeTab === tab ? "#1e1e28" : "transparent",
                    color: activeTab === tab ? "#e8e6e3" : "#5a5860",
                  }}
                >
                  {tab.charAt(0).toUpperCase() + tab.slice(1)}
                </button>
              ))}
            </div>

            {/* Tab Content */}
            <AnimatePresence mode="wait">
              {activeTab === "paper" && (
                <motion.div
                  key="paper"
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -8 }}
                  transition={{ duration: 0.2 }}
                  className="grid grid-cols-3 gap-2"
                >
                  {PAPERS.map((p) => (
                    <button
                      key={p.id}
                      onClick={() => setPaper(p)}
                      className="group relative p-3 rounded-lg text-left transition-all duration-200"
                      style={{
                        background: paper.id === p.id ? "#1e1e28" : "#141418",
                        border: `1px solid ${paper.id === p.id ? "#7c6fe044" : "#1e1e24"}`,
                      }}
                    >
                      <div
                        className="w-full h-8 rounded-sm mb-2 transition-transform duration-200 group-hover:scale-105"
                        style={{
                          background: p.color,
                          boxShadow: "inset 0 1px 3px rgba(0,0,0,0.08)",
                        }}
                      >
                        {(p.id === "college_ruled" || p.id === "legal_pad" || p.id === "sticky_note") && (
                          <svg className="w-full h-full">
                            {[0, 1, 2].map((i) => (
                              <line
                                key={i}
                                x1="8" y1={10 + i * 9} x2="92%" y2={10 + i * 9}
                                stroke={p.accent}
                                strokeWidth="0.5"
                                opacity="0.5"
                              />
                            ))}
                          </svg>
                        )}
                      </div>
                      <div className="text-[11px] font-medium" style={{ color: paper.id === p.id ? "#e8e6e3" : "#8a8890" }}>
                        {p.label}
                      </div>
                      <div className="text-[9px]" style={{ color: "#4a4850" }}>
                        {p.desc}
                      </div>
                    </button>
                  ))}
                </motion.div>
              )}

              {activeTab === "ink" && (
                <motion.div
                  key="ink"
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -8 }}
                  transition={{ duration: 0.2 }}
                  className="flex gap-3 flex-wrap"
                >
                  {INKS.map((i) => (
                    <button
                      key={i.id}
                      onClick={() => setInk(i)}
                      className="flex items-center gap-2.5 px-4 py-2.5 rounded-lg transition-all duration-200"
                      style={{
                        background: ink.id === i.id ? "#1e1e28" : "#141418",
                        border: `1px solid ${ink.id === i.id ? "#7c6fe044" : "#1e1e24"}`,
                      }}
                    >
                      <div className="w-3.5 h-3.5 rounded-full ring-1 ring-white/10" style={{ background: i.hex }} />
                      <span className="text-xs font-medium" style={{ color: ink.id === i.id ? "#e8e6e3" : "#6b6970" }}>
                        {i.label}
                      </span>
                    </button>
                  ))}
                </motion.div>
              )}

              {activeTab === "effects" && (
                <motion.div
                  key="effects"
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -8 }}
                  transition={{ duration: 0.2 }}
                  className="space-y-2"
                >
                  {EFFECTS.map((e) => (
                    <button
                      key={e.id}
                      onClick={() => setEffect(e)}
                      className="w-full flex items-center justify-between px-4 py-3 rounded-lg transition-all duration-200"
                      style={{
                        background: effect.id === e.id ? "#1e1e28" : "#141418",
                        border: `1px solid ${effect.id === e.id ? "#7c6fe044" : "#1e1e24"}`,
                      }}
                    >
                      <div>
                        <div className="text-xs font-medium" style={{ color: effect.id === e.id ? "#e8e6e3" : "#8a8890" }}>
                          {e.label}
                        </div>
                        <div className="text-[10px]" style={{ color: "#4a4850" }}>
                          {e.desc}
                        </div>
                      </div>
                      {effect.id === e.id && (
                        <motion.div
                          layoutId="effectCheck"
                          className="w-4 h-4 rounded-full flex items-center justify-center"
                          style={{ background: "#7c6fe0" }}
                        >
                          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="3">
                            <polyline points="20 6 9 17 4 12" />
                          </svg>
                        </motion.div>
                      )}
                    </button>
                  ))}
                </motion.div>
              )}
            </AnimatePresence>

            {/* Neatness Slider */}
            <div>
              <div className="flex justify-between items-center mb-2">
                <label className="text-xs font-medium" style={{ color: "#8a8890", letterSpacing: "0.06em" }}>
                  NEATNESS
                </label>
                <span className="text-[10px] tabular-nums" style={{ color: "#4a4850" }}>
                  {Math.round(neatness * 100)}%
                </span>
              </div>
              <input
                type="range"
                min="0"
                max="1"
                step="0.05"
                value={neatness}
                onChange={(e) => setNeatness(parseFloat(e.target.value))}
                className="w-full h-1 rounded-full appearance-none cursor-pointer"
                style={{
                  background: `linear-gradient(to right, #7c6fe0 ${neatness * 100}%, #2a2a30 ${neatness * 100}%)`,
                }}
              />
              <div className="flex justify-between mt-1">
                <span className="text-[9px]" style={{ color: "#4a4850" }}>Messy</span>
                <span className="text-[9px]" style={{ color: "#4a4850" }}>Pristine</span>
              </div>
            </div>

            {/* Generate Button */}
            <motion.button
              onClick={handleGenerate}
              disabled={isGenerating || !text.trim()}
              whileHover={{ scale: 1.01 }}
              whileTap={{ scale: 0.98 }}
              className="w-full py-3 rounded-lg text-sm font-semibold transition-all duration-200 disabled:opacity-40"
              style={{
                background: "linear-gradient(135deg, #7c6fe0, #5a4fc0)",
                color: "#ffffff",
                boxShadow: "0 4px 20px rgba(124, 111, 224, 0.25)",
              }}
            >
              {isGenerating ? (
                <span className="flex items-center justify-center gap-2">
                  <motion.span
                    animate={{ rotate: 360 }}
                    transition={{ duration: 1, repeat: Infinity, ease: "linear" }}
                    className="inline-block w-4 h-4 border-2 border-white/30 border-t-white rounded-full"
                  />
                  Generating...
                </span>
              ) : (
                "Generate Document"
              )}
            </motion.button>
          </motion.div>

          {/* Right Column — Preview */}
          <motion.div
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.5, delay: 0.2 }}
          >
            <label className="text-xs font-medium mb-2 block" style={{ color: "#8a8890", letterSpacing: "0.06em" }}>
              PREVIEW
            </label>
            <div
              className="rounded-lg overflow-hidden"
              style={{
                background: "#141418",
                border: "1px solid #1e1e24",
                boxShadow: "0 8px 40px rgba(0,0,0,0.3)",
              }}
            >
              <div className="p-4">
                <AnimatePresence mode="wait">
                  {generatedImage ? (
                    <motion.img
                      key="generated"
                      src={generatedImage}
                      initial={{ opacity: 0, scale: 0.95 }}
                      animate={{ opacity: 1, scale: 1 }}
                      exit={{ opacity: 0 }}
                      transition={{ duration: 0.4 }}
                      className="w-full rounded-sm"
                      alt="Generated handwriting"
                    />
                  ) : (
                    <motion.div key="preview" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
                      <HandwritingPreview text={text} ink={ink} paper={paper} isGenerating={isGenerating} />
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>

              {generatedImage && (
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  className="px-4 pb-4 flex gap-2"
                >
                  <a
                    href={generatedImage}
                    download="inkclone-output.png"
                    className="flex-1 py-2 rounded-md text-xs font-medium text-center transition-all duration-200"
                    style={{ background: "#1e1e28", color: "#8a8890", border: "1px solid #2a2a30" }}
                  >
                    Download PNG
                  </a>
                  <button
                    onClick={() => setGeneratedImage(null)}
                    className="px-4 py-2 rounded-md text-xs font-medium transition-all duration-200"
                    style={{ background: "#1e1e28", color: "#5a5860", border: "1px solid #2a2a30" }}
                  >
                    Clear
                  </button>
                </motion.div>
              )}
            </div>

            {/* Stats */}
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.5 }}
              className="grid grid-cols-3 gap-3 mt-4"
            >
              {[
                { label: "Glyphs", value: "142" },
                { label: "Characters", value: "39" },
                { label: "Papers", value: "6" },
              ].map((stat) => (
                <div
                  key={stat.label}
                  className="p-3 rounded-lg text-center"
                  style={{ background: "#141418", border: "1px solid #1e1e24" }}
                >
                  <div className="text-lg font-semibold" style={{ color: "#7c6fe0" }}>
                    {stat.value}
                  </div>
                  <div className="text-[9px] font-medium" style={{ color: "#4a4850", letterSpacing: "0.08em" }}>
                    {stat.label.toUpperCase()}
                  </div>
                </div>
              ))}
            </motion.div>
          </motion.div>
        </div>

        {/* Footer */}
        <motion.footer
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.8 }}
          className="mt-20 pt-6 text-center text-[10px]"
          style={{ borderTop: "1px solid #1a1a20", color: "#3a3840" }}
        >
          InkClone — Built by Vishnu Mahesha
        </motion.footer>
      </div>
    </div>
  );
}