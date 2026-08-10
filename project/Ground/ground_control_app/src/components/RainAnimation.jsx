import React, { useEffect, useRef } from 'react';

function RainAnimation({ humidity = 80 }) {
  const canvasRef = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    let animationFrameId;

    // Adjust canvas size to window size
    const resizeCanvas = () => {
      canvas.width = window.innerWidth;
      canvas.height = window.innerHeight;
    };
    resizeCanvas();
    window.addEventListener('resize', resizeCanvas);

    // Rain settings
    // Scaled by humidity (higher humidity = more rain)
    const maxDrops = Math.floor((humidity / 100) * 120); 
    const drops = [];
    const splashes = [];

    // Initialize drops
    for (let i = 0; i < maxDrops; i++) {
      drops.push({
        x: Math.random() * canvas.width,
        y: Math.random() * canvas.height - canvas.height,
        vy: 8 + Math.random() * 8, // Velocity Y
        vx: -1.5 - Math.random() * 1.5, // Velocity X (slight diagonal wind)
        len: 15 + Math.random() * 15, // Drop length
        opacity: 0.15 + Math.random() * 0.3,
        width: 1 + Math.random() * 0.8
      });
    }

    // Animation loop
    const animate = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      // Draw and update drops
      ctx.strokeStyle = 'rgba(14, 116, 144, 0.15)';
      for (let i = 0; i < drops.length; i++) {
        const d = drops[i];

        // Set width and opacity dynamically
        ctx.lineWidth = d.width;
        ctx.beginPath();
        ctx.moveTo(d.x, d.y);
        ctx.lineTo(d.x + d.vx, d.y + d.len);
        ctx.stroke();

        // Move drop
        d.y += d.vy;
        d.x += d.vx;

        // Reset if offscreen (bottom or sides)
        if (d.y > canvas.height) {
          // Add splash at the bottom before reset
          if (Math.random() < 0.3 && splashes.length < 50) {
            splashes.push({
              x: d.x,
              y: canvas.height - 2,
              radius: 1,
              maxRadius: 4 + Math.random() * 4,
              opacity: 0.6,
              vx: (Math.random() - 0.5) * 4,
              vy: -Math.random() * 3
            });
          }

          d.y = -20;
          d.x = Math.random() * canvas.width;
          d.vy = 8 + Math.random() * 8;
        }
        if (d.x < -20) {
          d.x = canvas.width + 20;
        }
      }

      // Draw and update splashes
      for (let i = splashes.length - 1; i >= 0; i--) {
        const s = splashes[i];
        ctx.strokeStyle = `rgba(14, 116, 144, ${s.opacity * 0.45})`;
        ctx.lineWidth = 1;
        ctx.beginPath();
        
        // Dynamic expanding ring
        ctx.arc(s.x, s.y, s.radius, 0, Math.PI * 2);
        ctx.stroke();

        // Update properties
        s.radius += 0.4;
        s.opacity -= 0.04;

        // Remove dead splashes
        if (s.opacity <= 0 || s.radius >= s.maxRadius) {
          splashes.splice(i, 1);
        }
      }

      animationFrameId = requestAnimationFrame(animate);
    };

    animate();

    return () => {
      window.removeEventListener('resize', resizeCanvas);
      cancelAnimationFrame(animationFrameId);
    };
  }, [humidity]);

  return (
    <canvas
      ref={canvasRef}
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        width: '100vw',
        height: '100vh',
        zIndex: 2, // Layered behind transparent cards (which are z-index: 10) but above bg-grid (z-index: 1)
        pointerEvents: 'none', // Ensure user clicks pass through the canvas
        mixBlendMode: 'screen'
      }}
    />
  );
}

export default RainAnimation;
