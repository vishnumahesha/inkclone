'use client'

import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Button } from '../components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card'
import { 
  PenTool, 
  Download, 
  Sparkles, 
  Zap, 
  FileText,
  Palette,
  Image as ImageIcon,
  ArrowRight,
  CheckCircle
} from 'lucide-react'

const paperTypes = [
  { id: 'college_ruled', name: 'College Ruled', emoji: '📝' },
  { id: 'blank', name: 'Blank Paper', emoji: '📄' },
  { id: 'dot_grid', name: 'Dot Grid', emoji: '⚡' },
  { id: 'legal_pad', name: 'Legal Pad', emoji: '📋' },
  { id: 'sticky_note', name: 'Sticky Note', emoji: '📝' },
]

const inkColors = [
  { id: 'black', name: 'Classic Black', color: 'bg-black' },
  { id: 'blue', name: 'Royal Blue', color: 'bg-blue-600' },
  { id: 'dark_blue', name: 'Navy Blue', color: 'bg-blue-900' },
  { id: 'red', name: 'Crimson Red', color: 'bg-red-600' },
  { id: 'green', name: 'Forest Green', color: 'bg-green-600' },
  { id: 'pencil', name: 'Graphite', color: 'bg-gray-500' },
]

const effects = [
  { id: 'scan', name: 'Scanner Effect', description: 'Professional scan appearance' },
  { id: 'phone', name: 'Phone Photo', description: 'Natural mobile capture look' },
  { id: 'clean', name: 'Clean Digital', description: 'Crisp, clear output' },
]

export default function InkClonePro() {
  const [text, setText] = useState("The quick brown fox jumps over the lazy dog")
  const [paper, setPaper] = useState('college_ruled')
  const [ink, setInk] = useState('black')
  const [effect, setEffect] = useState('scan')
  const [neatness, setNeatness] = useState(0.7)
  const [isGenerating, setIsGenerating] = useState(false)
  const [result, setResult] = useState<string | null>(null)

  const handleGenerate = async () => {
    setIsGenerating(true)
    
    try {
      const response = await fetch('/api/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          text,
          paper,
          ink,
          artifact: effect,
          neatness,
        }),
      })
      
      const data = await response.json()
      if (data.success) {
        setResult(data.image)
      }
    } catch (error) {
      console.error('Generation failed:', error)
    } finally {
      setIsGenerating(false)
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-blue-50/30 to-indigo-50/50">
      {/* Hero Section */}
      <div className="relative overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-r from-blue-600/20 to-purple-600/20"></div>
        <div className="relative px-6 pt-16 pb-12">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="text-center max-w-4xl mx-auto"
          >
            <div className="flex items-center justify-center gap-3 mb-6">
              <div className="p-3 glass rounded-2xl">
                <PenTool className="w-8 h-8 text-blue-600" />
              </div>
              <h1 className="text-5xl font-bold text-gradient">
                InkClone Pro
              </h1>
            </div>
            <p className="text-xl text-slate-600 mb-8 leading-relaxed">
              Transform your text into beautiful, realistic handwritten documents.
              <br />
              Professional quality with authentic handwriting simulation.
            </p>
            
            <div className="flex items-center justify-center gap-6 text-sm text-slate-500">
              <div className="flex items-center gap-2">
                <CheckCircle className="w-4 h-4 text-green-500" />
                <span>Real handwriting glyphs</span>
              </div>
              <div className="flex items-center gap-2">
                <CheckCircle className="w-4 h-4 text-green-500" />
                <span>5 paper types</span>
              </div>
              <div className="flex items-center gap-2">
                <CheckCircle className="w-4 h-4 text-green-500" />
                <span>Instant generation</span>
              </div>
            </div>
          </motion.div>
        </div>
      </div>

      {/* Main Interface */}
      <div className="px-6 pb-16">
        <div className="max-w-7xl mx-auto">
          <div className="grid lg:grid-cols-2 gap-8">
            
            {/* Controls Panel */}
            <motion.div
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              className="space-y-6"
            >
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <FileText className="w-5 h-5" />
                    Your Text
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <textarea
                    value={text}
                    onChange={(e) => setText(e.target.value)}
                    className="w-full h-32 p-4 glass rounded-xl border-0 resize-none focus:outline-none focus:ring-2 focus:ring-blue-500 transition-all"
                    placeholder="Type the text you want to render as handwriting..."
                  />
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <Palette className="w-5 h-5" />
                    Paper & Style
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-6">
                  {/* Paper Types */}
                  <div>
                    <label className="block text-sm font-medium text-slate-700 mb-3">Paper Type</label>
                    <div className="grid grid-cols-3 gap-2">
                      {paperTypes.map((paperType) => (
                        <motion.button
                          key={paperType.id}
                          whileHover={{ scale: 1.02 }}
                          whileTap={{ scale: 0.98 }}
                          onClick={() => setPaper(paperType.id)}
                          className={`p-3 rounded-xl text-xs font-medium transition-all ${
                            paper === paperType.id
                              ? 'bg-gradient-to-r from-blue-500 to-purple-600 text-white shadow-lg'
                              : 'glass hover:bg-white/80'
                          }`}
                        >
                          <div className="text-lg mb-1">{paperType.emoji}</div>
                          {paperType.name}
                        </motion.button>
                      ))}
                    </div>
                  </div>

                  {/* Ink Colors */}
                  <div>
                    <label className="block text-sm font-medium text-slate-700 mb-3">Ink Color</label>
                    <div className="grid grid-cols-3 gap-2">
                      {inkColors.map((inkColor) => (
                        <motion.button
                          key={inkColor.id}
                          whileHover={{ scale: 1.02 }}
                          whileTap={{ scale: 0.98 }}
                          onClick={() => setInk(inkColor.id)}
                          className={`p-3 rounded-xl text-xs font-medium transition-all ${
                            ink === inkColor.id
                              ? 'bg-gradient-to-r from-blue-500 to-purple-600 text-white shadow-lg'
                              : 'glass hover:bg-white/80'
                          }`}
                        >
                          <div className={`w-4 h-4 rounded-full mx-auto mb-1 ${inkColor.color}`}></div>
                          {inkColor.name}
                        </motion.button>
                      ))}
                    </div>
                  </div>

                  {/* Effects */}
                  <div>
                    <label className="block text-sm font-medium text-slate-700 mb-3">Effect</label>
                    <div className="space-y-2">
                      {effects.map((eff) => (
                        <motion.button
                          key={eff.id}
                          whileHover={{ scale: 1.01 }}
                          onClick={() => setEffect(eff.id)}
                          className={`w-full p-3 rounded-xl text-left transition-all ${
                            effect === eff.id
                              ? 'bg-gradient-to-r from-blue-500 to-purple-600 text-white shadow-lg'
                              : 'glass hover:bg-white/80'
                          }`}
                        >
                          <div className="font-medium text-sm">{eff.name}</div>
                          <div className={`text-xs ${effect === eff.id ? 'text-blue-100' : 'text-slate-500'}`}>
                            {eff.description}
                          </div>
                        </motion.button>
                      ))}
                    </div>
                  </div>

                  {/* Neatness */}
                  <div>
                    <label className="block text-sm font-medium text-slate-700 mb-3">
                      Neatness: {Math.round(neatness * 100)}%
                    </label>
                    <input
                      type="range"
                      min="0"
                      max="1"
                      step="0.1"
                      value={neatness}
                      onChange={(e) => setNeatness(parseFloat(e.target.value))}
                      className="w-full h-2 glass rounded-full appearance-none cursor-pointer"
                    />
                    <div className="flex justify-between text-xs text-slate-500 mt-1">
                      <span>Messy</span>
                      <span>Perfect</span>
                    </div>
                  </div>
                </CardContent>
              </Card>

              <Button
                onClick={handleGenerate}
                disabled={isGenerating || !text.trim()}
                variant="primary"
                size="lg"
                className="w-full"
              >
                <AnimatePresence mode="wait">
                  {isGenerating ? (
                    <motion.div
                      key="generating"
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      exit={{ opacity: 0 }}
                      className="flex items-center gap-2"
                    >
                      <motion.div
                        animate={{ rotate: 360 }}
                        transition={{ duration: 1, repeat: Infinity, ease: "linear" }}
                      >
                        <Sparkles className="w-5 h-5" />
                      </motion.div>
                      Generating Handwriting...
                    </motion.div>
                  ) : (
                    <motion.div
                      key="generate"
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      exit={{ opacity: 0 }}
                      className="flex items-center gap-2"
                    >
                      <Zap className="w-5 h-5" />
                      Generate Document
                      <ArrowRight className="w-4 h-4" />
                    </motion.div>
                  )}
                </AnimatePresence>
              </Button>
            </motion.div>

            {/* Preview Panel */}
            <motion.div
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              className="lg:sticky lg:top-6"
            >
              <Card className="h-[600px] flex flex-col">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <ImageIcon className="w-5 h-5" />
                    Preview
                  </CardTitle>
                </CardHeader>
                <CardContent className="flex-1 flex items-center justify-center">
                  <AnimatePresence mode="wait">
                    {result ? (
                      <motion.div
                        key="result"
                        initial={{ opacity: 0, scale: 0.9 }}
                        animate={{ opacity: 1, scale: 1 }}
                        exit={{ opacity: 0, scale: 0.9 }}
                        className="w-full h-full flex flex-col"
                      >
                        <div className="flex-1 flex items-center justify-center bg-slate-50 rounded-xl overflow-hidden">
                          <img
                            src={result}
                            alt="Generated handwriting"
                            className="max-w-full max-h-full object-contain"
                          />
                        </div>
                        <div className="mt-4 flex gap-2">
                          <Button variant="secondary" size="sm" className="flex-1">
                            <Download className="w-4 h-4 mr-2" />
                            Download PNG
                          </Button>
                        </div>
                      </motion.div>
                    ) : (
                      <motion.div
                        key="placeholder"
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        className="text-center text-slate-400"
                      >
                        <FileText className="w-16 h-16 mx-auto mb-4 opacity-50" />
                        <p className="text-lg font-medium mb-2">Your document will appear here</p>
                        <p className="text-sm">Configure your settings and click generate</p>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </CardContent>
              </Card>
            </motion.div>
          </div>
        </div>
      </div>
    </div>
  )
}
