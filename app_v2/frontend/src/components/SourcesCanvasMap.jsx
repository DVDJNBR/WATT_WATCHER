import { useEffect, useRef, useState } from 'react'

// The entire canvas is built inside a one-shot useEffect, so React Fast
// Refresh re-renders the component without ever re-running it: edits to the
// drawing code applied to nothing and the old canvas kept running until a
// manual hard reload. decline() doesn't help — the React plugin registers its
// own Fast Refresh boundary and wins — so force a real reload.
if (import.meta.hot) import.meta.hot.accept(() => window.location.reload())

// ── Constants ──────────────────────────────────────────────────────────────
const SRC_COLORS_DARK  = {nucleaire:'#a78bfa',hydraulique:'#60a5fa',solaire:'#f59e0b',eolien:'#10b981',thermique:'#f87171',autre:'#9a9a9e'}
const SRC_COLORS_LIGHT = {nucleaire:'#7c3aed',hydraulique:'#3b82f6',solaire:'#d97706',eolien:'#059669',thermique:'#dc2626',autre:'#71717a'}
/**
 * Idle sites (solar under cloud, wind in a lull).
 *
 * Chosen by luminance, not hue: a dot recedes when it sits level with the map
 * behind it. Measured against the clear-sky map — L*48 dark, L*98 light — the
 * previous picks were 25 and 68 points *below* it, so they punched dark holes
 * and drew the eye as much as a lit site would. These sit level with their own
 * theme's map (L*46 / L*78) at a low chroma: present, clearly not producing.
 */
export const OFF_COLORS = {
  dark:  { solaire:'#7e6954', eolien:'#547464' },
  light: { solaire:'#d8bca7', eolien:'#a6c9b7' },
}
const FILIERES = ['nucleaire','hydraulique','solaire','eolien','thermique','autre']
const F_LABEL  = {nucleaire:'Nucléaire',hydraulique:'Hydraulique',solaire:'Solaire',eolien:'Éolien',thermique:'Thermique',autre:'Autre'}
const _NATIONAL_MW = {nucleaire:63100,hydraulique:25800,eolien:24100,solaire:78700,thermique:20000,autre:5000}
const R_MIN=2.0, R_MAX=7.0
const DLON=0.75,DLAT=0.75,G_LON0=-5.0,G_LAT0=41.0,G_NCOL=22,G_NROW=16
// Cloud raster resolution. The field is quantised into 10-point bands, but at
// 160×112 each cell covered ~5 screen px, so the bilinear upscale melted the
// bands back into one continuous gradient — the strata stopped reading as
// steps. Rasterising near screen resolution keeps each band's edge sharp while
// smoothing stays on (turning it off just brings back visible pixel blocks).
const OW=400,OH=280

// ── Dark-theme cloud ladder ────────────────────────────────────────────────
// The landmass is an opaque DARK_BASE_L % grey and cloud is a black veil laid
// over it, in 10-point bands: a clear sky paints nothing at all (alpha 0, the
// map shows through untouched) and full cover is solid black (alpha 1), with
// the bands in between ramping linearly.
//
// Anchoring the two ends on transparency rather than on absolute luminosities
// is what makes DARK_BASE_L meaningful: the map's own brightness is what a
// clear sky reveals, so raising it lifts the whole map without touching the
// "100 % cover reads black" end of the scale.
// Separation between two neighbouring strata is DARK_BASE_L / (CLOUD_BANDS-1):
// the clear-sky and full-cover ends are pinned, so the base luminosity is the
// only room the in-between rungs have to spread out. Adding bands without
// raising it just packs them tighter — 45 % over 8 bands buys the same 16-point
// spacing that 5 bands had at 25 %, on a noticeably lighter map.
const DARK_BASE_L    = 45
const DARK_BASE_GREY = `rgb(${Math.round(255*DARK_BASE_L/100)},${Math.round(255*DARK_BASE_L/100)},${Math.round(255*DARK_BASE_L/100)})`
// Band width, in cover-%. Fewer, wider bands put more opacity between one
// stratum and the next, so the steps read at a glance; at 10 % the rungs were
// only ~11 % of alpha apart and blurred into one another.
const CLOUD_STEP     = 12.5
const CLOUD_BANDS    = Math.round(100/CLOUD_STEP)  // 8: 0–12.5 %, 12.5–25 % … 87.5–100 %
// Rung spacing isn't uniform: luminosity falls as (1−t)^CLOUD_GAMMA, which with
// gamma < 1 keeps the bright rungs close together and opens a wide drop into
// the final black band — overcast reads as a distinct mass rather than as one
// more step. At 1 the ladder is evenly spaced again.
const CLOUD_GAMMA    = 0.6
/** Black-veil alpha (0–1) for a cloud-cover percentage, per the ladder above. */
function cloudAlpha(cover){
  const band=Math.max(0,Math.min(CLOUD_BANDS-1,Math.floor(cover/CLOUD_STEP)))
  const t=band/(CLOUD_BANDS-1)
  return 1-Math.pow(1-t,CLOUD_GAMMA)
}

/**
 * The cloud ladder as swatches, clear sky first — for the legend gauge.
 *
 * Exported from here on purpose: a legend that restates the scale by hand
 * drifts the moment CLOUD_STEP or the gamma is tweaked, and this scale has
 * already been retuned several times. Rendering it from the same function the
 * map paints with means the two cannot disagree.
 *
 * Swatches are the veil itself, so the first one is genuinely transparent and
 * shows whatever the legend sits on — exactly what a clear sky does on the map.
 */
/**
 * What the map's landmass shows with no cloud on it — the backing a legend
 * gauge needs behind the veil swatches, so the transparent end reads as the
 * clear-sky map rather than as the page behind the legend.
 */
export function cloudScaleBase(dark){
  return dark ? DARK_BASE_GREY : 'transparent'
}

export function cloudScale(dark){
  return Array.from({length:CLOUD_BANDS},(_,band)=>{
    const a=1-Math.pow(1-band/(CLOUD_BANDS-1),CLOUD_GAMMA)
    return {
      from: Math.round(band*CLOUD_STEP),
      to:   Math.round((band+1)*CLOUD_STEP),
      color: dark ? `rgba(0,0,0,${a.toFixed(3)})` : `rgba(40,52,80,${(a*110/255).toFixed(3)})`,
    }
  })
}
const NPART=55,SPEED=0.12,MAX_AGE=150,UVS=8,POOL_SIZE=500
// Trail is now an explicit position history redrawn each frame (see startAnim),
// so its length is a segment count rather than a per-frame decay factor.
const TRAIL_LEN=14
// Wind sits WIND_TONES rungs of the cloud ladder away from whatever the map
// shows beneath it — lighter in dark theme, darker in light. TRAIL_SPREAD is
// how far head and tail straddle that offset, so the head always comes out the
// lighter end and the tail the darker one.
const WIND_TONES=1, WIND_TRAIL_SPREAD=2
// Floor on the trail's own luminance. The tint is an offset *added to the
// local map*, so over the black overcast band the whole trail lands near 0 and
// all but disappears, while over clear map it rides on 115 and shouts. Same
// offset either way — what differs is that the eye, adapted to the bright
// parts of the map, can't resolve a near-black trail on near-black ground.
// Scaling the floor by t keeps the head-to-tail gradient instead of clamping
// the trail flat.
const WIND_MIN_L=48
// Grey quantisation for batching trail segments into colour buckets.
const WIND_QUANT=8
// Light theme reference luminances: the paper, and the slate wash at full
// opacity, used to work out what the map shows under a particle.
const LIGHT_PAPER_L=250, LIGHT_WASH_L=52, MAX_WASH_A=110/255
// Tight bounds: France métropolitaine sans Corse, bien zoomée
const LON_MIN=-4.8,LON_MAX=8.4,LAT_MIN=42.8,LAT_MAX=51.1,PAD=22
const METEO_API = '/api/v1/meteo/grid'
const PROD_API  = '/api/v1/production/regional'
const PROD_COLOR = '#2dd4bf'

function hexRgb(h){return[parseInt(h.slice(1,3),16),parseInt(h.slice(3,5),16),parseInt(h.slice(5,7),16)]}
function rgba(h,a){const c=hexRgb(h);return`rgba(${c[0]},${c[1]},${c[2]},${a})`}

function mercLat(lat){const p=lat*Math.PI/180;return Math.log(Math.tan(Math.PI/4+p/2))}
const YMN=mercLat(LAT_MIN),YMX=mercLat(LAT_MAX)
// Geographic aspect ratio (width/height) of France in Mercator — ~1.26
const GEO_AR=(LON_MAX-LON_MIN)*Math.PI/180/(YMX-YMN)

// bicubic helpers
function gv(arr,ci,ri){return arr[Math.max(0,Math.min(G_NROW-1,ri))*G_NCOL+Math.max(0,Math.min(G_NCOL-1,ci))]}
function cubicH(p0,p1,p2,p3,t){return 0.5*((2*p1)+(-p0+p2)*t+(2*p0-5*p1+4*p2-p3)*t*t+(-p0+3*p1-3*p2+p3)*t*t*t)}
function bicubic(arr,gx,gy){
  const ci=Math.floor(gx),ri=Math.floor(gy),tx=gx-ci,ty=gy-ri
  const rows=[]
  for(let dr=-1;dr<=2;dr++) rows.push(cubicH(gv(arr,ci-1,ri+dr),gv(arr,ci,ri+dr),gv(arr,ci+1,ri+dr),gv(arr,ci+2,ri+dr),tx))
  return cubicH(rows[0],rows[1],rows[2],rows[3],ty)
}

/** @param {{ selectedCode?: string }} props */
export default function SourcesCanvasMap({ selectedCode = '' }) {
  const mapRef          = useRef(null)
  const windRef         = useRef(null)
  const ptsRef          = useRef(null)
  const rebuildRef      = useRef(null)
  const drawRef         = useRef(null)
  const selectedCodeRef = useRef(selectedCode)
  const s               = useRef({})
  const [loading,  setLoading]  = useState(true)
  const [mixNote,  setMixNote]  = useState('Chargement mix…')
  const [mixTs,    setMixTs]    = useState('')
  const [tooltip,  setTooltip]  = useState(null)
  // isDarkTheme drives the legend colours in JSX (canvas reads isDark() inline)
  const [isDarkTheme, setIsDarkTheme] = useState(() => {
    const t = document.documentElement.getAttribute('data-theme')
    if (t === 'dark') return true
    if (t === 'light') return false
    return window.matchMedia('(prefers-color-scheme:dark)').matches
  })

  // Sync selectedCode prop → ref → redraw
  useEffect(() => {
    selectedCodeRef.current = selectedCode
    drawRef.current?.()
  }, [selectedCode])

  useEffect(() => {
    const canvas  = mapRef.current
    const wCanvas = windRef.current
    const pCanvas = ptsRef.current
    if(!canvas || !wCanvas || !pCanvas) return
    const ctx  = canvas.getContext('2d')
    const wctx = wCanvas.getContext('2d')
    const pctx = pCanvas.getContext('2d')
    const dpr  = Math.max(1, window.devicePixelRatio || 1)

    // ── mutable state ────────────────────────────────────────────────────
    let W=0, H=0
    let drawW=0, drawH=0, offX=0, offY=0
    let REGIONS={}, regionPaths={}, regionCentroids={}, francePath=new Path2D()
    let heroPts=[], hoveredHero=-1
    let _installedMW={}, _filiereMax={}
    let _capFactor={nucleaire:1,hydraulique:1,eolien:1,solaire:1,thermique:1,autre:1}
    let _siteCF=[], _weatherGrid=[]
    let _cloudGrid=null, _ugrid=null, _vgrid=null
    let _cloudRasterCanvas=null, _rasterDark=null
    let uvU=null, uvV=null, uvC=null, _uvW=0, _uvH=0
    let MW2=0, MH2=0, franceMask=null
    let particles=[], spawnPool=[], animRAF=null
    let mixInterval=null, _sprData=null

    function isDark(){
      const t=document.documentElement.getAttribute('data-theme')
      if(t==='dark') return true; if(t==='light') return false
      return window.matchMedia('(prefers-color-scheme:dark)').matches
    }

    // Letterbox: fit France's true Mercator aspect ratio into canvas
    function updateDims(){
      if(W<=0||H<=0){drawW=0;drawH=0;offX=PAD;offY=PAD;return}
      const avW=W-2*PAD, avH=H-2*PAD
      if(avW/avH>GEO_AR){drawH=avH;drawW=drawH*GEO_AR;offX=(W-drawW)/2;offY=PAD}
      else{drawW=avW;drawH=drawW/GEO_AR;offX=PAD;offY=(H-drawH)/2}
    }
    function proj(lon,lat){
      return[offX+(lon-LON_MIN)/(LON_MAX-LON_MIN)*drawW,
             offY+(1-(mercLat(lat)-YMN)/(YMX-YMN))*drawH]
    }
    function unproj(px,py,cW,cH){
      const sx=cW/W||1, sy=cH/H||1
      const lon=LON_MIN+(px/sx-offX)/drawW*(LON_MAX-LON_MIN)
      const m=YMN+(1-(py/sy-offY)/drawH)*(YMX-YMN)
      return[lon,(2*Math.atan(Math.exp(m))-Math.PI/2)*180/Math.PI]
    }

    // ── cloud raster ─────────────────────────────────────────────────────
    // Isobands, the way a forecast chart draws them: quantise AFTER the
    // interpolation, never before. Banding the coarse field first makes every
    // boundary follow a cell edge — the blocky "Minecraft" look — because the
    // steps are baked in before anything smooths them. Interpolating the
    // continuous field up to screen resolution first and only then cutting it
    // into bands puts each boundary on a true iso-line of the field, so it
    // comes out as a clean curve.
    function buildRaster(){
      if(!_cloudGrid||W<=0||H<=0) return
      const dark=isDark(); _rasterDark=dark

      // 1. Continuous field (no banding yet) at working resolution.
      const fc=document.createElement('canvas'); fc.width=OW; fc.height=OH
      const fx=fc.getContext('2d')
      const fimg=fx.createImageData(OW,OH); const fpx=fimg.data
      for(let row=0;row<OH;row++){
        for(let col=0;col<OW;col++){
          const ll=unproj(col/OW*W,row/OH*H,W,H)
          const gx=(ll[0]-G_LON0)/DLON, gy=(ll[1]-G_LAT0)/DLAT
          const v=Math.max(0,Math.min(100,bicubic(_cloudGrid,gx,gy)))
          const o=(row*OW+col)*4, b=Math.round(v*2.55)
          fpx[o]=b;fpx[o+1]=b;fpx[o+2]=b;fpx[o+3]=255
        }
      }
      fx.putImageData(fimg,0,0)

      // 2. Smooth upscale to device resolution — this interpolation is what
      //    the band edges will later be carved out of.
      const RW=Math.max(1,Math.round(W*dpr)), RH=Math.max(1,Math.round(H*dpr))
      const oc=document.createElement('canvas'); oc.width=RW; oc.height=RH
      const ox=oc.getContext('2d')
      ox.imageSmoothingEnabled=true; ox.imageSmoothingQuality='high'
      ox.drawImage(fc,0,0,RW,RH)

      // 3. Band each output pixel. Edges land on iso-lines, one device pixel
      //    wide, so they read as crisp curves rather than staircases.
      const img=ox.getImageData(0,0,RW,RH); const px=img.data
      const MAX_ALPHA=110  // light: slate-blue wash, deeper than the old 80
      const [cr,cg,cb]=dark?[0,0,0]:[40,52,80]
      for(let i=0;i<RW*RH;i++){
        const o=i*4
        const cover=px[o]/2.55
        // Dark follows the banded veil (transparent at clear sky, black at
        // full cover); light keeps the simple linear wash.
        const alpha=dark
          ? Math.round(255*cloudAlpha(cover))
          : Math.round(MAX_ALPHA*cloudAlpha(cover))
        px[o]=cr;px[o+1]=cg;px[o+2]=cb;px[o+3]=alpha
      }
      ox.putImageData(img,0,0); _cloudRasterCanvas=oc
    }

    // ── UV wind map ───────────────────────────────────────────────────────
    function buildUVMap(){
      if(!_ugrid||!_vgrid) return
      _uvW=Math.ceil(W/UVS)+1; _uvH=Math.ceil(H/UVS)+1
      uvU=new Float32Array(_uvW*_uvH); uvV=new Float32Array(_uvW*_uvH)
      // Cloud cover rides along on the same lattice as the wind field: the
      // particle tint needs it per-particle per-frame, and sampling this grid
      // is a couple of lookups where a fresh bicubic would be ~16.
      uvC=_cloudGrid?new Float32Array(_uvW*_uvH):null
      for(let r=0;r<_uvH;r++) for(let c=0;c<_uvW;c++){
        const ll=unproj(c*UVS,r*UVS,W,H)
        const gx=(ll[0]-G_LON0)/DLON, gy=(ll[1]-G_LAT0)/DLAT
        uvU[r*_uvW+c]=bicubic(_ugrid,gx,gy)
        uvV[r*_uvW+c]=bicubic(_vgrid,gx,gy)
        if(uvC) uvC[r*_uvW+c]=Math.max(0,Math.min(100,bicubic(_cloudGrid,gx,gy)))
      }
    }
    /** Cloud cover (0–100) under a canvas point, bilinear on the UV lattice. */
    function cloudAt(x,y){
      if(!uvC) return 0
      const c=x/UVS,r=y/UVS,ci=Math.floor(c),ri=Math.floor(r),tx=c-ci,ty=r-ri
      const bi=(ci2,ri2)=>uvC[Math.max(0,Math.min(_uvH-1,ri2))*_uvW+Math.max(0,Math.min(_uvW-1,ci2))]
      return (1-tx)*((1-ty)*bi(ci,ri)+ty*bi(ci,ri+1))+tx*((1-ty)*bi(ci+1,ri)+ty*bi(ci+1,ri+1))
    }
    function windAt(x,y){
      const c=x/UVS,r=y/UVS,ci=Math.floor(c),ri=Math.floor(r),tx=c-ci,ty=r-ri
      const bi=(arr,ci2,ri2)=>arr[Math.max(0,Math.min(_uvH-1,ri2))*_uvW+Math.max(0,Math.min(_uvW-1,ci2))]
      const u=(1-tx)*((1-ty)*bi(uvU,ci,ri)+ty*bi(uvU,ci,ri+1))+tx*((1-ty)*bi(uvU,ci+1,ri)+ty*bi(uvU,ci+1,ri+1))
      const v=(1-tx)*((1-ty)*bi(uvV,ci,ri)+ty*bi(uvV,ci,ri+1))+tx*((1-ty)*bi(uvV,ci+1,ri)+ty*bi(uvV,ci+1,ri+1))
      return[u,v]
    }

    // ── France mask ───────────────────────────────────────────────────────
    function buildFranceMask(){
      MW2=Math.ceil(W/2)+1; MH2=Math.ceil(H/2)+1
      const mc=document.createElement('canvas'); mc.width=MW2; mc.height=MH2
      const mx=mc.getContext('2d'); mx.fillStyle='#000'
      Object.values(regionPaths).forEach(p2=>{
        mx.save(); mx.setTransform(0.5,0,0,0.5,0,0); mx.fill(p2); mx.restore()
      })
      franceMask=mx.getImageData(0,0,MW2,MH2).data
    }
    function inFrance(x,y){
      const cx=Math.round(x/2),cy=Math.round(y/2)
      if(cx<0||cy<0||cx>=MW2||cy>=MH2) return false
      return franceMask[(cy*MW2+cx)*4+3]>128
    }

    // ── Particles ─────────────────────────────────────────────────────────
    function buildSpawnPool(){
      spawnPool=[]
      let tries=0
      while(spawnPool.length<POOL_SIZE&&tries<20000){
        tries++
        const x=offX+Math.random()*drawW, y=offY+Math.random()*drawH
        if(inFrance(x,y)) spawnPool.push([x,y])
      }
    }
    function randomSpawn(){
      const s=spawnPool[Math.floor(Math.random()*spawnPool.length)]
      return s||[W/2,H/2]
    }
    function initParticles(){
      particles=[]
      for(let i=0;i<NPART;i++){
        const s=randomSpawn()
        particles.push({x:s[0],y:s[1],age:Math.floor(Math.random()*MAX_AGE),trail:[[s[0],s[1]]]})
      }
    }
    function respawn(p){
      const s=randomSpawn()
      p.x=s[0]; p.y=s[1]; p.age=0; p.trail=[[s[0],s[1]]]
    }

    /**
     * Wind stroke colour at a point, derived from the map *as composited under
     * the clouds there* and offset by WIND_TONES rungs of the cloud ladder.
     *
     * This is what sells the illusion: the particle canvas sits above
     * everything in the DOM, but a trail crossing an overcast cell is tinted
     * off that cell's near-black, so it darkens exactly as if the weather were
     * passing over it. Keeping the offset in ladder rungs rather than fixed
     * greys means it tracks DARK_BASE_L and CLOUD_BANDS automatically.
     *
     * @param t 0 at the tail of the trail, 1 at the head — head always ends up
     *          the lighter of the two, tail the darker, in both themes.
     */
    function windGrey(x,y,t,dark){
      const cover=cloudAt(x,y)
      const tone=(255*DARK_BASE_L/100)/(CLOUD_BANDS-1)
      // Luminance the map actually shows here, clouds included.
      const localL=dark
        ? (255*DARK_BASE_L/100)*(1-cloudAlpha(cover))
        : LIGHT_PAPER_L+(LIGHT_WASH_L-LIGHT_PAPER_L)*(MAX_WASH_A*cloudAlpha(cover))
      const dir=dark?1:-1
      let L=localL+dir*tone*(WIND_TONES+(t-0.5)*WIND_TRAIL_SPREAD)
      // Keep the trail off the floor in dark theme (see WIND_MIN_L); the head
      // gets the full floor, the tail 40 % of it, so the gradient survives.
      if(dark) L=Math.max(L,WIND_MIN_L*(0.4+0.6*t))
      // Snapped to WIND_QUANT so segments collapse into a handful of colour
      // buckets: per-segment strokeStyle would mean ~700 stroke() calls a
      // frame, where bucketing keeps it to one per distinct tone.
      const g=Math.max(0,Math.min(255,Math.round(L)))
      return Math.round(g/WIND_QUANT)*WIND_QUANT
    }

    function startAnim(){
      if(animRAF) cancelAnimationFrame(animRAF)
      function tick(){
        const dark=isDark()
        wctx.save(); wctx.setTransform(dpr,0,0,dpr,0,0)
        // Trails are redrawn from stored history every frame rather than left
        // to decay on the canvas: a fading buffer can only make old strokes
        // more transparent, never recolour them, so head and tail could not
        // differ in tone.
        wctx.clearRect(0,0,W,H)
        wctx.lineWidth=1.8; wctx.lineCap='round'
        const buckets=new Map()
        for(let i=0;i<particles.length;i++){
          const p=particles[i], uv=windAt(p.x,p.y)
          const spd=Math.sqrt(uv[0]*uv[0]+uv[1]*uv[1])
          // Calm zone: no visible trail, just respawn
          if(spd<0.5){respawn(p);continue}
          // UV × SPEED: speed and trail length both proportional to wind magnitude
          const nx=p.x+uv[0]*SPEED, ny=p.y+uv[1]*SPEED
          p.age++
          if(p.age>MAX_AGE||!inFrance(nx,ny)){respawn(p);continue}
          p.x=nx; p.y=ny
          p.trail.push([nx,ny])
          if(p.trail.length>TRAIL_LEN) p.trail.shift()

          const n=p.trail.length
          for(let k=1;k<n;k++){
            const a=p.trail[k-1], b=p.trail[k]
            const g=windGrey((a[0]+b[0])/2,(a[1]+b[1])/2,k/(n-1),dark)
            let path=buckets.get(g)
            if(!path){path=new Path2D();buckets.set(g,path)}
            path.moveTo(a[0],a[1]); path.lineTo(b[0],b[1])
          }
        }
        const alpha=dark?0.55:0.5
        buckets.forEach((path,g)=>{
          wctx.strokeStyle=`rgba(${g},${g},${g},${alpha})`
          wctx.stroke(path)
        })
        wctx.restore()
        animRAF=requestAnimationFrame(tick)
      }
      tick()
    }

    // ── Paths ─────────────────────────────────────────────────────────────
    function buildPaths(){
      regionPaths={}; regionCentroids={}; francePath=new Path2D()
      Object.keys(REGIONS).forEach(code=>{
        const p2=new Path2D(); const pts=[]
        REGIONS[code].paths.forEach(ring=>{
          ring.forEach((pt,i)=>{
            const xy=proj(pt[0],pt[1])
            if(i===0){p2.moveTo(xy[0],xy[1]);francePath.moveTo(xy[0],xy[1])}
            else{p2.lineTo(xy[0],xy[1]);francePath.lineTo(xy[0],xy[1])}
            pts.push(xy)
          })
          p2.closePath(); francePath.closePath()
        })
        regionPaths[code]=p2
        let cx=0,cy=0; pts.forEach(p=>{cx+=p[0];cy+=p[1]})
        regionCentroids[code]=[cx/pts.length,cy/pts.length]
      })
    }
    function buildPoints(units){
      heroPts=[]; _installedMW={}; _filiereMax={}
      units.forEach(u=>{
        const f=u.filiere||'autre', mw=u.cap_mw||0
        _installedMW[f]=(_installedMW[f]||0)+mw
        _filiereMax[f]=Math.max(_filiereMax[f]||0,mw)
        const xy=proj(u.lon,u.lat)
        heroPts.push({x:xy[0],y:xy[1],f,mw,name:u.name,region:u.region||'',lat:u.lat,lon:u.lon})
      })
      heroPts.sort((a,b)=>a.mw-b.mw)
    }

    // ── Draw ──────────────────────────────────────────────────────────────
    function drawCloudRaster(){
      if(!_cloudGrid) return
      if(_rasterDark!==isDark()) buildRaster()
      if(!_cloudRasterCanvas) return
      ctx.save(); ctx.clip(francePath)
      // The raster is already at device resolution, so this lands 1:1 and no
      // resampling occurs either way; smoothing stays off so a rounding
      // mismatch can never soften the band edges.
      ctx.imageSmoothingEnabled=false
      ctx.drawImage(_cloudRasterCanvas,0,0,W,H)
      ctx.restore()
    }
    function draw(){
      ctx.save(); ctx.setTransform(dpr,0,0,dpr,0,0); ctx.clearRect(0,0,W,H)
      const dark=isDark()
      const selCode=selectedCodeRef.current

      // Map fills — light theme stays airy, strokes carry the borders.
      // Dark: an opaque DARK_BASE_L grey rather than a translucent white, so
      // the landmass has one known luminosity for the cloud ladder in
      // buildRaster to darken from. Translucent white composited over the
      // page background gave a value that drifted with whatever sat behind.
      const mapFillBase  = dark ? DARK_BASE_GREY : 'rgba(100,95,90,.05)'
      const mapFillDim   = dark ? 'rgb(28,28,28)' : 'rgba(100,95,90,.02)'
      const mapStrokeBase= dark ? 'rgba(255,255,255,.14)' : 'rgba(20,20,22,.02)'
      const mapStrokeDim = dark ? 'rgba(255,255,255,.05)' : 'rgba(20,20,22,.01)'
      const labelColBase = dark ? 'rgba(255,255,255,.45)' : 'rgba(20,20,22,.45)'
      const labelColDim  = dark ? 'rgba(255,255,255,.15)' : 'rgba(20,20,22,.15)'

      Object.keys(regionPaths).forEach(code=>{
        const dimmed = !!(selCode && code !== selCode)
        ctx.fillStyle = dimmed ? mapFillDim : mapFillBase
        ctx.fill(regionPaths[code])
        ctx.strokeStyle = dimmed ? mapStrokeDim : mapStrokeBase
        ctx.lineWidth=0.8; ctx.stroke(regionPaths[code])
      })
      // Accent stroke on selected region
      if(selCode && regionPaths[selCode]){
        ctx.strokeStyle='rgba(45,212,191,0.60)'; ctx.lineWidth=1.5
        ctx.stroke(regionPaths[selCode])
      }
      drawCloudRaster()
      ctx.font='500 11px -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif'
      ctx.textAlign='center'
      Object.keys(regionCentroids).forEach(code=>{
        const dimmed = !!(selCode && code !== selCode)
        ctx.fillStyle = dimmed ? labelColDim : labelColBase
        const c=regionCentroids[code]; ctx.fillText(REGIONS[code].nom,c[0],c[1])
      })
      ctx.restore()
      drawPoints()
    }

    /**
     * Power plants, on their own canvas stacked above the wind layer.
     *
     * They used to share the map canvas, which sits *below* the particles, so
     * trails crossed over every site. Splitting them out is the only way to
     * get map → clouds → wind → plants in that order, since each layer has to
     * composite over the one beneath it.
     */
    function drawPoints(){
      pctx.save(); pctx.setTransform(dpr,0,0,dpr,0,0); pctx.clearRect(0,0,W,H)
      if(!heroPts.length){pctx.restore();return}
      const dark=isDark()
      const colors=dark?SRC_COLORS_DARK:SRC_COLORS_LIGHT
      const selCode=selectedCodeRef.current
      const selNom=selCode?(REGIONS[selCode]?.nom||''):''
      const ctx=pctx  // keep the drawing calls below verbatim

      // Proportional circle radius — sqrt to avoid huge circles at large sizes
      const rScale=Math.sqrt(Math.min(W,H)/480)

      heroPts.forEach((p,i)=>{
        const inSel = !selCode || p.region === selNom
        const scf=_siteCF.length?Math.max(0,_siteCF[i]||0):Math.max(0,_capFactor[p.f]||0)
        const norm=p.mw/(_filiereMax[p.f]||p.mw||1)
        const coreR=(R_MIN+Math.sqrt(norm)*(R_MAX-R_MIN))*rScale
        const col=colors[p.f]

        if(!inSel){
          ctx.beginPath();ctx.arc(p.x,p.y,coreR,0,Math.PI*2)
          ctx.fillStyle=rgba(col,0.07);ctx.fill()
          return
        }

        // Off states sit on top of the cloud layer, which now reaches pure
        // black at full cover — the old dark alphas (.12 fill / .25 stroke)
        // were set against a mid-grey map and vanished entirely over an
        // overcast cell. Brighter hue + firmer alpha keeps a stopped site
        // readable whatever the weather above it.
        if(p.f==='solaire'&&scf<0.03){
          const vc=dark?OFF_COLORS.dark.solaire:OFF_COLORS.light.solaire
          ctx.beginPath();ctx.arc(p.x,p.y,coreR,0,Math.PI*2)
          ctx.fillStyle=rgba(vc,dark?0.48:0.40);ctx.fill()
          ctx.beginPath();ctx.arc(p.x,p.y,coreR,0,Math.PI*2)
          ctx.strokeStyle=rgba(vc,dark?0.85:0.80);ctx.lineWidth=0.9;ctx.stroke()
          return
        }
        // Same absolute bar as solar above (3 % of nameplate). The old 0.02
        // was the real reason off éolien went unnoticed: wind's scf ceiling is
        // ~5x lower than solar's, so that bar caught only 25 % of wind sites
        // against 57 % of solar ones — a colour difference with almost nothing
        // to colour. At 0.03 it marks 45 %, which is honest: with wind at 4 %
        // of national capacity, most farms really are idle.
        if(p.f==='eolien'&&scf<0.03){
          const vc=dark?OFF_COLORS.dark.eolien:OFF_COLORS.light.eolien
          ctx.beginPath();ctx.arc(p.x,p.y,coreR,0,Math.PI*2)
          ctx.fillStyle=rgba(vc,dark?0.48:0.40);ctx.fill()
          ctx.beginPath();ctx.arc(p.x,p.y,coreR,0,Math.PI*2)
          ctx.strokeStyle=rgba(vc,dark?0.85:0.80);ctx.lineWidth=0.9;ctx.stroke()
          return
        }
        // Active: visible base + strong sector so on/off is unmistakable in light theme
        ctx.beginPath();ctx.arc(p.x,p.y,coreR,0,Math.PI*2);ctx.fillStyle=rgba(col,dark?0.25:0.28);ctx.fill()
        if(scf>0.01){
          ctx.beginPath();ctx.moveTo(p.x,p.y)
          ctx.arc(p.x,p.y,coreR,-Math.PI/2,-Math.PI/2+scf*2*Math.PI)
          ctx.closePath();ctx.fillStyle=rgba(col,dark?0.80:0.82);ctx.fill()
        }
        ctx.beginPath();ctx.arc(p.x,p.y,coreR,0,Math.PI*2)
        ctx.strokeStyle=rgba(col,dark?0.50:0.55);ctx.lineWidth=0.8;ctx.stroke()
      })
      if(hoveredHero>=0&&hoveredHero<heroPts.length){
        const p=heroPts[hoveredHero]
        const norm=p.mw/(_filiereMax[p.f]||p.mw||1)
        const r=(R_MIN+Math.sqrt(norm)*(R_MAX-R_MIN))*rScale+5
        ctx.beginPath();ctx.arc(p.x,p.y,r,0,Math.PI*2)
        ctx.strokeStyle=rgba(colors[p.f],0.9);ctx.lineWidth=1.5;ctx.stroke()
      }
      ctx.restore()
    }

    // expose draw so the selectedCode effect can trigger redraws
    drawRef.current = draw

    // ── Nearest grid ──────────────────────────────────────────────────────
    function _nearestGrid(lat,lon){
      if(!_cloudGrid) return null
      let bestI=0,bestD=Infinity
      for(let ri=0;ri<G_NROW;ri++) for(let ci=0;ci<G_NCOL;ci++){
        const la=G_LAT0+ri*DLAT,lo=G_LON0+ci*DLON
        const d=(la-lat)**2+(lo-lon)**2
        if(d<bestD){bestD=d;bestI=ri*G_NCOL+ci}
      }
      return bestI
    }

    // ── Data fetching ─────────────────────────────────────────────────────
    function loadWeather(){
      fetch(METEO_API).then(r=>r.json()).then(resp=>{
        const arr=(resp&&resp.data)||[]
        _cloudGrid=new Float32Array(G_NROW*G_NCOL)
        _ugrid=new Float32Array(G_NROW*G_NCOL)
        _vgrid=new Float32Array(G_NROW*G_NCOL)
        _weatherGrid=new Array(G_NROW*G_NCOL)
        for(let k=0;k<G_NROW*G_NCOL;k++){
          _cloudGrid[k]=0;_ugrid[k]=0;_vgrid[k]=0
          _weatherGrid[k]={lat:0,lon:0,cloud:0,wind:5,windDir:0}
        }
        arr.forEach(pt=>{
          const ri=Math.round((pt.lat-G_LAT0)/DLAT)
          const ci=Math.round((pt.lon-G_LON0)/DLON)
          if(ri<0||ri>=G_NROW||ci<0||ci>=G_NCOL) return
          const idx=ri*G_NCOL+ci
          const wd=pt.wind_direction*Math.PI/180
          _cloudGrid[idx]=pt.cloud_cover
          _ugrid[idx]=-pt.wind_speed*Math.sin(wd)
          _vgrid[idx]=pt.wind_speed*Math.cos(wd)
          _weatherGrid[idx]={lat:pt.lat,lon:pt.lon,cloud:pt.cloud_cover,wind:pt.wind_speed,windDir:pt.wind_direction}
        })
        _siteCF=heroPts.map(p=>{
          const baseCF=_capFactor[p.f]||0
          if(p.f==='solaire'||p.f==='eolien'){
            const gi=_nearestGrid(p.lat,p.lon)
            if(gi!==null){
              if(p.f==='solaire') return baseCF*(1-_cloudGrid[gi]/100)
              if(p.f==='eolien')  return baseCF*Math.min(1,_weatherGrid[gi].wind/10)
            }
          }
          return baseCF
        })
        buildRaster(); buildUVMap(); buildFranceMask(); buildSpawnPool(); initParticles(); startAnim(); draw()
        rebuildRef.current=()=>{buildRaster();draw()}
      }).catch(()=>{_siteCF=heroPts.map(p=>_capFactor[p.f]||0)})
    }

    function loadMix(){
      const today=new Date().toISOString().slice(0,10)
      const yesterday=new Date(Date.now()-86400000).toISOString().slice(0,10)
      fetch(`${PROD_API}?start_date=${yesterday}&end_date=${today}&limit=300`)
        .then(r=>r.json()).then(resp=>{
          const arr=resp.data||[]; if(!arr.length){setMixNote('Mix indisponible');return}
          // Newest *complete* timestamp, not simply the newest. Regions don't
          // land in one write, so the freshest slice routinely holds a single
          // region — summing that as the national mix reported éol./sol. at
          // 0 GW and left the map with no wind or solar sites lit up.
          const byTs=new Map()
          for(const r of arr) byTs.set(r.timestamp,(byTs.get(r.timestamp)||0)+1)
          const full=Math.max(...byTs.values())
          const latest=[...byTs.entries()]
            .filter(([,n])=>n===full)
            .reduce((mx,[ts])=>ts>mx?ts:mx,'')
          const latestRows=arr.filter(r=>r.timestamp===latest)
          const actual={nucleaire:0,hydraulique:0,eolien:0,solaire:0,thermique:0,autre:0}
          latestRows.forEach(r=>{
            Object.entries(r.sources||{}).forEach(([src,v])=>{
              if(v>0){const f=src==='bioenergies'?'autre':src; if(actual[f]!==undefined) actual[f]+=v}
            })
          })
          FILIERES.forEach(f=>{const inst=_NATIONAL_MW[f]||_installedMW[f]||1;_capFactor[f]=Math.min(1,actual[f]/inst)})
          // UTC: horodatage is stored UTC, so rendering in local time would
          // shift the map's "Màj" 2 h ahead of the data it describes.
          const ts=latest?new Date(latest.replace(' ','T')).toLocaleTimeString('fr-FR',{hour:'2-digit',minute:'2-digit',timeZone:'UTC'}):''
          setMixTs('Màj '+ts)
          const parts=['nucl. '+Math.round(actual.nucleaire/1000)+'GW','hydro '+Math.round(actual.hydraulique/1000)+'GW','éol. '+Math.round(actual.eolien/1000)+'GW','sol. '+Math.round(actual.solaire/1000)+'GW','therm. '+Math.round(actual.thermique/1000)+'GW']
          setMixNote(parts.join(' · '))
          _siteCF=heroPts.map(p=>{
            const baseCF=_capFactor[p.f]||0
            if(_cloudGrid&&(p.f==='solaire'||p.f==='eolien')){
              const gi=_nearestGrid(p.lat,p.lon)
              if(gi!==null){
                if(p.f==='solaire') return baseCF*(1-_cloudGrid[gi]/100)
                if(p.f==='eolien')  return baseCF*Math.min(1,_weatherGrid[gi]?.wind/10||0)
              }
            }
            return baseCF
          })
          draw(); loadWeather()
        }).catch(()=>setMixNote('Mix indisponible'))
    }

    // ── Resize ────────────────────────────────────────────────────────────
    function resize(){
      const rect=canvas.getBoundingClientRect()
      W=rect.width; H=rect.height
      canvas.width=Math.round(W*dpr); canvas.height=Math.round(H*dpr)
      wCanvas.width=Math.round(W*dpr); wCanvas.height=Math.round(H*dpr)
      pCanvas.width=Math.round(W*dpr); pCanvas.height=Math.round(H*dpr)
      updateDims()
      buildPaths()
      if(_sprData) buildPoints(_sprData)
      if(_cloudGrid){buildRaster();buildUVMap();buildFranceMask();buildSpawnPool();if(particles.length) initParticles()}
      draw()
    }

    // ── Hover ─────────────────────────────────────────────────────────────
    function onMouseMove(e){
      const rect=canvas.getBoundingClientRect()
      const mx=e.clientX-rect.left, my=e.clientY-rect.top
      const rScale=Math.sqrt(Math.min(W,H)/480)
      let found=-1, bestD=Infinity
      heroPts.forEach((p,i)=>{
        const norm=p.mw/(_filiereMax[p.f]||p.mw||1)
        const r=(R_MIN+Math.sqrt(norm)*(R_MAX-R_MIN))*rScale+4
        const d=Math.sqrt((mx-p.x)**2+(my-p.y)**2)
        if(d<=r&&d<bestD){bestD=d;found=i}
      })
      if(found!==hoveredHero){hoveredHero=found;draw()}
      if(found>=0){
        const p=heroPts[found]
        const scf=_siteCF.length?Math.max(0,_siteCF[found]||0):Math.max(0,_capFactor[p.f]||0)
        setTooltip({name:p.name,type:F_LABEL[p.f],region:p.region,
          mw:p.mw>=1000?(p.mw/1000).toFixed(2)+' GW':p.mw+' MW',
          live:scf>0.01?'≈ '+Math.round(p.mw*scf)+' MW produits ('+Math.round(scf*100)+'%)':'à l\'arrêt',
          x:e.clientX-rect.left, y:e.clientY-rect.top})
        canvas.style.cursor='pointer'
      } else {setTooltip(null);canvas.style.cursor='default'}
    }
    function onMouseLeave(){if(hoveredHero!==-1){hoveredHero=-1;draw()};setTooltip(null);canvas.style.cursor='default'}

    canvas.addEventListener('mousemove',onMouseMove)
    canvas.addEventListener('mouseleave',onMouseLeave)

    // ── Init ──────────────────────────────────────────────────────────────
    Promise.all([
      fetch('/units-combined.json').then(r=>r.json()),
      fetch('/france-regions.geojson').then(r=>r.json()),
    ]).then(([units,gj])=>{
      gj.features.forEach(f=>{
        if(f.properties.code==='94') return  // Corse: no data in pipeline
        const rings=f.geometry.type==='MultiPolygon'
          ?f.geometry.coordinates.map(p=>p[0])
          :[f.geometry.coordinates[0]]
        REGIONS[f.properties.code]={nom:f.properties.nom,paths:rings}
      })
      updateDims(); buildPaths(); _sprData=units; buildPoints(units); setLoading(false); draw(); loadMix()
      mixInterval=setInterval(loadMix,5*60*1000)
    }).catch(e=>{console.error(e);setLoading(false)})

    const ro=new ResizeObserver(()=>resize())
    ro.observe(canvas)
    setTimeout(resize,0)

    // ── Cleanup ───────────────────────────────────────────────────────────
    return ()=>{
      drawRef.current=null
      if(animRAF) cancelAnimationFrame(animRAF)
      if(mixInterval) clearInterval(mixInterval)
      canvas.removeEventListener('mousemove',onMouseMove)
      canvas.removeEventListener('mouseleave',onMouseLeave)
      ro.disconnect()
    }
  }, [])

  // Theme observer — rebuild raster + redraw + update isDarkTheme state
  useEffect(()=>{
    const mo=new MutationObserver(()=>{
      const t=document.documentElement.getAttribute('data-theme')
      const dark=t==='dark'||(t!=='light'&&window.matchMedia('(prefers-color-scheme:dark)').matches)
      setIsDarkTheme(dark)
      rebuildRef.current?.()
    })
    mo.observe(document.documentElement,{attributes:true,attributeFilter:['data-theme']})
    return ()=>mo.disconnect()
  },[])

  // Legend: current-theme filière colours + prod/conso line symbols
  const filiereColors = isDarkTheme ? SRC_COLORS_DARK : SRC_COLORS_LIGHT
  const consoLegendColor = isDarkTheme ? '#e8e8e6' : '#1c1b1a'

  return (
    <div style={{position:'relative',width:'100%',height:'100%',display:'flex',flexDirection:'column'}}>
      <div style={{position:'relative',flex:'1 1 0',minHeight:0}}>
        <canvas
          ref={mapRef}
          style={{display:'block',width:'100%',height:'100%',cursor:'default'}}
        />
        {/* Stacking order is the compositing order: map + clouds, then wind,
            then plants on top — so trails pass behind every site. */}
        <canvas
          ref={windRef}
          style={{position:'absolute',top:0,left:0,width:'100%',height:'100%',pointerEvents:'none'}}
        />
        <canvas
          ref={ptsRef}
          style={{position:'absolute',top:0,left:0,width:'100%',height:'100%',pointerEvents:'none'}}
        />
        {loading && (
          <div style={{position:'absolute',inset:0,display:'flex',alignItems:'center',justifyContent:'center',fontSize:13,color:'var(--color-text-2)'}}>
            Chargement…
          </div>
        )}
        {tooltip && (
          <div style={{
            position:'absolute',pointerEvents:'none',zIndex:10,
            left:tooltip.x,top:tooltip.y,
            transform:'translate(-50%,calc(-100% - 14px))',
            background:'var(--color-surface-1)',border:'1px solid var(--color-border)',
            borderRadius:8,padding:'9px 13px',minWidth:150,
            boxShadow:'0 6px 20px rgba(0,0,0,.2)',fontSize:12,lineHeight:1.55
          }}>
            <p style={{fontWeight:700,fontSize:12.5,margin:'0 0 3px'}}>{tooltip.name}</p>
            <p style={{color:'var(--color-text-2)',margin:'0 0 1px'}}>{tooltip.type}</p>
            <p style={{color:'var(--color-text-2)',margin:'0 0 1px',fontSize:11}}>{tooltip.region}</p>
            <p style={{fontWeight:600,margin:0}}>{tooltip.mw} installés</p>
            <p style={{color:'var(--color-text-2)',margin:'2px 0 0',fontSize:11}}>{tooltip.live}</p>
          </div>
        )}
        {mixNote && (
          <div style={{position:'absolute',bottom:8,right:10,pointerEvents:'none',fontSize:10.5,color:'var(--color-text-2)',opacity:.7,whiteSpace:'nowrap'}}>
            {mixNote}
          </div>
        )}
      </div>
    </div>
  )
}
