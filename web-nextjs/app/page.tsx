'use client'

import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Button } from '../components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs'
import { Separator } from '../components/ui/separator'
import { 
  PenTool, 
  Download, 
  Sparkles, 
  Zap, 
  FileText,
  Palette,
  Image as ImageIcon,
  ArrowRight,
  CheckCircle,
  Github,
  Star,
  Settings,
  Wand2,
  Eye,
  Grid
} from 'lucide-react'

const paperTypes = [
  { id: 'college_ruled', name: 'College Ruled', emoji: '📝', description: 'Standard ruled paper for notes' },
  { id: 'blank', name: 'Blank Paper', emoji: '📄', description: 'Clean white paper' },
  { id: 'dot_grid', name: 'Dot Grid', emoji: '⚡', description: 'Subtle dot pattern' },
  { id: 'legal_pad', name: 'Legal Pad', emoji: '📋', description: 'Yellow legal pad style' },
  { id: 'sticky_note', name: 'Sticky Note', emoji: '🟡', description: 'Small yellow note' },
  { id: 'index_card', name: 'Index Card', emoji: '🗃️', description: '3x5 index card' },
]

const inkColors = [
  { id: 'black', name: 'Classic Black', color: 'bg-black', hex: '#000000' },
  { id: 'blue', name: 'Royal Blue', color: 'bg-blue-600', hex: '#2563eb' },
  { id: 'dark_blue', name: 'Navy Blue', color: 'bg-blue-900', hex: '#1e3a8a' },
  { id: 'red', name: 'Crimson Red', color: 'bg-red-600', hex: '#dc2626' },
  { id: 'green', name: 'Forest Green', color: 'bg-green-600', hex: '#16a34a' },
  { id: 'pencil', name: 'Graphite', color: 'bg-gray-500', hex: '#6b7280' },
]

const effects = [
  { id: 'scan', name: 'Scanner Effect', description: 'Professional scan appearance', icon: Grid },
  { id: 'phone', name: 'Phone Photo', description: 'Natural mobile capture look', icon: Eye },
  { id: 'clean', name: 'Clean Digital', description: 'Crisp, clear output', icon: Sparkles },
]

const presets = [
  { name: 'Student Notes', paper: 'college_ruled', ink: 'blue', effect: 'clean', neatness: 0.8 },
  { name: 'Quick Sketch', paper: 'blank', ink: 'pencil', effect: 'phone', neatness: 0.6 },
  { name: 'Professional', paper: 'legal_pad', ink: 'black', effect: 'scan', neatness: 0.9 },
  { name: 'Casual', paper: 'sticky_note', ink: 'blue', effect: 'phone', neatness: 0.5 },
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

  const applyPreset = (preset: typeof presets[0]) => {
    setPaper(preset.paper)
    setInk(preset.ink)
    setEffect(preset.effect)
    setNeatness(preset.neatness)
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
              <motion.a
                href="https://github.com/vishnu-mahesha/inkclone"
                target="_blank"
                rel="noopener noreferrer"
                className="p-2 glass rounded-lg hover:bg-white/80 transition-all"
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
              >
                <Github className="w-6 h-6 text-slate-600" />
              </motion.a>
            </div>
            <p className="text-xl text-slate-600 mb-8 leading-relaxed">
              Transform your text into beautiful, realistic handwritten documents.
              <br />
              Professional quality with authentic handwriting simulation.
            </p>
            
            <div className="flex items-center justify-center gap-6 text-sm text-slate-500 mb-8">
              <div className="flex items-center gap-2">
                <CheckCircle className="w-4 h-4 text-green-500" />
                <span>142 real glyphs</span>
              </div>
              <div className="flex items-center gap-2">
                <CheckCircle className="w-4 h-4 text-green-500" />
                <span>6 paper types</span>
              </div>
              <div className="flex items-center gap-2">
                <CheckCircle className="w-4 h-4 text-green-500" />
                <span>Instant generation</span>
              </div>
              <div className="flex items-center gap-2">
                <Star className="w-4 h-4 text-yellow-500" />
                <span>Open source</span>
              </div>
            </div>
            
            {/* Quick Presets */}
            <div className="flex items-center justify-center gap-2 flex-wrap">
              {presets.map((preset) => (
                <motion.button
                  key={preset.name}
                  onClick={() => applyPreset(preset)}
                  className="px-4 py-2 text-xs font-medium glass rounded-lg hover:bg-white/80 transition-all"
                  whileHover={{ scale: 1.02 }}
                  whileTap={{ scale: 0.98 }}
                >
                  ✨ {preset.name}
                </motion.button>
              ))}
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
                    className="w-full h-32 p-4 glass rounded-xl border-0 resize-none focus:outline-none focus:ring-2 focus:ring-blue-500 transition-all placeholder:text-slate-400"
                    placeholder="Type the text you want to render as handwriting..."
                  />
                  <div className="mt-2 text-xs text-slate-500">
                    {text.length} characters
                  </div>
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <Settings className="w-5 h-5" />
                    Style Configuration
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <Tabs defaultValue="paper" className="w-full">
                    <TabsList className="grid w-full grid-cols-3">
                      <TabsTrigger value="paper">Paper</TabsTrigger>
                      <TabsTrigger value="ink">Ink</TabsTrigger>
                      <TabsTrigger value="effects">Effects</TabsTrigger>
                    </TabsList>
                    
                    <TabsContent value="paper" className="mt-6">
                      <div className="grid grid-cols-2 gap-3">
                        {paperTypes.map((paperType) => (
                          <motion.button
                            key={paperType.id}
                            whileHover={{ scale: 1.02 }}
                            whileTap={{ scale: 0.98 }}
                            onClick={() => setPaper(paperType.id)}
                            className={`p-4 rounded-xl text-left transition-all ${
                              paper === paperType.id
                                ? 'bg-gradient-to-r from-blue-500 to-purple-600 text-white shadow-lg'
                                : 'glass hover:bg-white/80'
                            }`}
                          >
                            <div className="text-2xl mb-2">{paperType.emoji}</div>
                            <div className="font-medium text-sm">{paperType.name}</div>
                            <div className={`text-xs mt-1 ${paper === paperType.id ? 'text-blue-100' : 'text-slate-500'}`}>
                              {paperType.description}
                            </div>
                          </motion.button>
                        ))}
                      </div>
                    </TabsContent>

                    <TabsContent value="ink" className="mt-6">
                      <div className="grid grid-cols-2 gap-3">
                        {inkColors.map((inkColor) => (
                          <motion.button
                            key={inkColor.id}
                            whileHover={{ scale: 1.02 }}
                            whileTap={{ scale: 0.98 }}
                            onClick={() => setInk(inkColor.id)}
                            className={`p-4 rounded-xl text-left transition-all ${
                              ink === inkColor.id
                                ? 'bg-gradient-to-r from-blue-500 to-purple-600 text-white shadow-lg'
                                : 'glass hover:bg-white/80'
                            }`}
                          >
                            <div className="flex items-center gap-3 mb-2">
                              <div className={`w-5 h-5 rounded-full ${inkColor.color} shadow-sm`}></div>
                              <div className="font-medium text-sm">{inkColor.name}</div>
                            </div>
                            <div className={`text-xs ${ink === inkColor.id ? 'text-blue-100' : 'text-slate-500'}`}>
                              {inkColor.hex}
                            </div>
                          </motion.button>
                        ))}
                      </div>
                    </TabsContent>

                    <TabsContent value="effects" className="mt-6">
                      <div className="space-y-3">
                        {effects.map((eff) => {
                          const IconComponent = eff.icon
                          return (
                            <motion.button
                              key={eff.id}
                              whileHover={{ scale: 1.01 }}
                              onClick={() => setEffect(eff.id)}
                              className={`w-full p-4 rounded-xl text-left transition-all flex items-center gap-3 ${
                                effect === eff.id
                                  ? 'bg-gradient-to-r from-blue-500 to-purple-600 text-white shadow-lg'
                                  : 'glass hover:bg-white/80'
                              }`}
                            >
                              <IconComponent className="w-5 h-5" />
                              <div>
                                <div className="font-medium text-sm">{eff.name}</div>
                                <div className={`text-xs ${effect === eff.id ? 'text-blue-100' : 'text-slate-500'}`}>
                                  {eff.description}
                                </div>
                              </div>
                            </motion.button>
                          )
                        })}
                      </div>
                    </TabsContent>
                  </Tabs>

                  <Separator className="my-6" />

                  {/* Neatness Slider */}
                  <div>
                    <label className="block text-sm font-medium text-slate-700 mb-3">
                      Handwriting Neatness: {Math.round(neatness * 100)}%
                    </label>
                    <div className="relative">
                      <input
                        type="range"
                        min="0"
                        max="1"
                        step="0.1"
                        value={neatness}
                        onChange={(e) => setNeatness(parseFloat(e.target.value))}
                        className="w-full h-2 glass rounded-full appearance-none cursor-pointer slider"
                      />
                      <div 
                        className="absolute top-0 h-2 bg-gradient-to-r from-blue-500 to-purple-600 rounded-full pointer-events-none"
                        style={{ width: `${neatness * 100}%` }}
                      />
                    </div>
                    <div className="flex justify-between text-xs text-slate-500 mt-1">
                      <span>🖊️ Messy</span>
                      <span>✨ Perfect</span>
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
                        <Wand2 className="w-5 h-5" />
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
              <Card className="h-[700px] flex flex-col">
                <CardHeader>
                  <CardTitle className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <ImageIcon className="w-5 h-5" />
                      Live Preview
                    </div>
                    {result && (
                      <Button variant="secondary" size="sm">
                        <Download className="w-4 h-4 mr-2" />
                        Download
                      </Button>
                    )}
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
                        <div className="flex-1 flex items-center justify-center bg-slate-50 rounded-xl overflow-hidden border-2 border-slate-100">
                          <img
                            src={result}
                            alt="Generated handwriting"
                            className="max-w-full max-h-full object-contain"
                          />
                        </div>
                        <div className="mt-4 flex gap-2">
                          <Button variant="secondary" size="sm" className="flex-1">
                            <Download className="w-4 h-4 mr-2" />
                            PNG
                          </Button>
                          <Button variant="ghost" size="sm" className="flex-1">
                            <Eye className="w-4 h-4 mr-2" />
                            Zoom
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
                        <div className="w-24 h-24 mx-auto mb-4 rounded-full glass flex items-center justify-center">
                          <FileText className="w-12 h-12 opacity-50" />
                        </div>
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

<style jsx global>{`
  .slider::-webkit-slider-thumb {
    appearance: none;
    height: 16px;
    width: 16px;
    border-radius: 50%;
    background: linear-gradient(135deg, #3b82f6, #9333ea);
    cursor: pointer;
    box-shadow: 0 2px 6px rgba(0,0,0,0.2);
  }
  
  .slider::-moz-range-thumb {
    height: 16px;
    width: 16px;
    border-radius: 50%;
    background: linear-gradient(135deg, #3b82f6, #9333ea);
    cursor: pointer;
    border: none;
    box-shadow: 0 2px 6px rgba(0,0,0,0.2);
  }
`}</style>