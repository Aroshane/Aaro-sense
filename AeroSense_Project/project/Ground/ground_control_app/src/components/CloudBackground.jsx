import React, { useEffect, useRef } from 'react';

function CloudBackground() {
  const canvasRef = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    let animationFrameId;

    const resizeCanvas = () => {
      canvas.width = window.innerWidth;
      canvas.height = window.innerHeight;
    };
    resizeCanvas();
    window.addEventListener('resize', resizeCanvas);

    // Initialize fluffy daytime clouds
    const clouds = [];
    const numClouds = 8;
    for (let i = 0; i < numClouds; i++) {
      clouds.push({
        x: Math.random() * (canvas.width + 400) - 200,
        y: Math.random() * (canvas.height * 0.5), // upper half of screen
        scale: 0.6 + Math.random() * 1.2,
        speed: 0.12 + Math.random() * 0.18, // slow horizontal drift
        opacity: 0.03 + Math.random() * 0.05, // subtle background mist
        circles: Array.from({ length: 5 }, (_, idx) => ({
          dx: (idx - 2) * (20 + Math.random() * 15),
          dy: (Math.random() - 0.5) * 12,
          r: 25 + Math.random() * 35
        }))
      });
    }

    // Initialize background flying companion drones
    const drones = [];
    const numDrones = 4;
    for (let i = 0; i < numDrones; i++) {
      drones.push({
        x: Math.random() * canvas.width,
        y: 80 + Math.random() * (canvas.height * 0.4), // flying space
        speedX: 0.5 + Math.random() * 0.8, // fly from left to right
        speedY: 0,
        wobbleSpeed: 0.02 + Math.random() * 0.03,
        wobbleRange: 5 + Math.random() * 10,
        wobbleOffset: Math.random() * 100,
        scale: 0.4 + Math.random() * 0.5, // tiny background drones for depth
        propAngle: 0,
        color: ['#ff5500', '#06b6d4', '#10b981', '#ff8833'][i % 4] // matching GCS branding
      });
    }

    const drawDrone = (ctx, d, time) => {
      ctx.save();
      
      // Calculate vertical hovering wobble (sine wave)
      const wobble = Math.sin(time * d.wobbleSpeed + d.wobbleOffset) * d.wobbleRange;
      ctx.translate(d.x, d.y + wobble);
      ctx.scale(d.scale, d.scale);
      
      // Propeller spin calculation
      d.propAngle += 0.4;
      
      // 1. Draw drone structural arms (carbon fibre rods)
      ctx.strokeStyle = '#1e293b';
      ctx.lineWidth = 4;
      ctx.beginPath();
      // Diagonal arms
      ctx.moveTo(-30, -18);
      ctx.lineTo(30, 18);
      ctx.moveTo(30, -18);
      ctx.lineTo(-30, 18);
      ctx.stroke();

      // 2. Draw motors & spinning propellers on four ends
      const motorPos = [
        { x: -30, y: -18 },
        { x: 30, y: -18 },
        { x: -30, y: 18 },
        { x: 30, y: 18 }
      ];

      motorPos.forEach(p => {
        // Motor pod body
        ctx.fillStyle = '#475569';
        ctx.beginPath();
        ctx.arc(p.x, p.y, 5, 0, Math.PI * 2);
        ctx.fill();

        // Propeller disc sweep glow
        ctx.strokeStyle = 'rgba(255, 255, 255, 0.6)';
        ctx.lineWidth = 2.5;
        ctx.beginPath();
        const px = Math.cos(d.propAngle) * 15;
        const py = Math.sin(d.propAngle) * 4; // elliptic compression for 3D perspective
        ctx.moveTo(p.x - px, p.y - py);
        ctx.lineTo(p.x + px, p.y + py);
        ctx.stroke();
      });

      // 3. Central battery / camera mount
      ctx.fillStyle = '#0f172a';
      ctx.beginPath();
      ctx.roundRect(-15, -6, 30, 12, 4);
      ctx.fill();

      // 4. Canopy dome with colored indicator decal
      ctx.fillStyle = d.color;
      ctx.beginPath();
      ctx.arc(0, -3, 10, 0, Math.PI, true);
      ctx.fill();

      // 5. Flashing collision avoidance beacon light (Red)
      const flash = Math.floor(time / 200) % 2 === 0;
      if (flash) {
        ctx.fillStyle = '#ef4444';
        ctx.beginPath();
        ctx.arc(0, 8, 3, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillStyle = 'rgba(239, 68, 68, 0.4)';
        ctx.beginPath();
        ctx.arc(0, 8, 9, 0, Math.PI * 2);
        ctx.fill();
      }

      ctx.restore();
    };

    let frameCount = 0;
    const animate = () => {
      frameCount++;
      // Clean previous frame
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      // 1. Draw glowing Sun in the top right
      const sunX = canvas.width - 160;
      const sunY = 130;
      const sunRadius = 55;

      // Outer golden sun glow
      const sunGlow = ctx.createRadialGradient(sunX, sunY, 0, sunX, sunY, 180);
      sunGlow.addColorStop(0, 'rgba(255, 253, 220, 0.2)');
      sunGlow.addColorStop(0.2, 'rgba(255, 136, 51, 0.08)');
      sunGlow.addColorStop(0.5, 'rgba(255, 85, 0, 0.02)');
      sunGlow.addColorStop(1, 'rgba(255, 255, 255, 0)');
      
      ctx.fillStyle = sunGlow;
      ctx.beginPath();
      ctx.arc(sunX, sunY, 180, 0, Math.PI * 2);
      ctx.fill();

      // Sun core
      ctx.fillStyle = 'rgba(255, 253, 220, 0.35)';
      ctx.beginPath();
      ctx.arc(sunX, sunY, sunRadius, 0, Math.PI * 2);
      ctx.fill();

      // 2. Draw fluffy white clouds
      clouds.forEach(c => {
        c.circles.forEach(circle => {
          const cx = c.x + circle.dx * c.scale;
          const cy = c.y + circle.dy * c.scale;
          const r = circle.r * c.scale;

          const grad = ctx.createRadialGradient(cx, cy, 0, cx, cy, r);
          // Pure white clouds with soft shadow overlay
          grad.addColorStop(0, `rgba(255, 255, 255, ${c.opacity})`);
          grad.addColorStop(0.4, `rgba(255, 255, 255, ${c.opacity * 0.95})`);
          grad.addColorStop(0.8, `rgba(240, 244, 250, ${c.opacity * 0.8})`); // soft blue-grey bottom tint
          grad.addColorStop(1, 'rgba(255, 255, 255, 0)');

          ctx.fillStyle = grad;
          ctx.beginPath();
          ctx.arc(cx, cy, r, 0, Math.PI * 2);
          ctx.fill();
        });

        // Move cloud
        c.x += c.speed;

        // Reset offscreen
        if (c.x > canvas.width + 300) {
          c.x = -300;
          c.y = Math.random() * (canvas.height * 0.5);
        }
      });

      // 3. Draw flying drones in background sky
      drones.forEach(d => {
        drawDrone(ctx, d, frameCount * 16);
        
        // Fly forward
        d.x += d.speedX;

        // Reset to left side
        if (d.x > canvas.width + 150) {
          d.x = -150;
          d.y = 80 + Math.random() * (canvas.height * 0.4);
        }
      });

      animationFrameId = requestAnimationFrame(animate);
    };

    animate();

    return () => {
      window.removeEventListener('resize', resizeCanvas);
      cancelAnimationFrame(animationFrameId);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        width: '100vw',
        height: '100vh',
        zIndex: 1, // Draw behind UI panels
        pointerEvents: 'none'
      }}
    />
  );
}

export default CloudBackground;
