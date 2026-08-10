document.addEventListener('DOMContentLoaded', () => {
    const initSky = () => {
        const skyCanvas = document.getElementById('sky-canvas');
        if (!skyCanvas) {
            setTimeout(initSky, 100);
            return;
        }

        const sCtx = skyCanvas.getContext('2d');

        const resizeSkyCanvas = () => {
            skyCanvas.width = window.innerWidth;
            skyCanvas.height = window.innerHeight;
        };
        resizeSkyCanvas();
        window.addEventListener('resize', resizeSkyCanvas);

        // Soft Light Clouds
        const skyClouds = [];
        const numSkyClouds = 8;
        for (let i = 0; i < numSkyClouds; i++) {
            skyClouds.push({
                x: Math.random() * (window.innerWidth + 400) - 200,
                y: Math.random() * (window.innerHeight * 0.45),
                scale: 0.8 + Math.random() * 1.2,
                speed: 0.05 + Math.random() * 0.08,
                opacity: 0.4 + Math.random() * 0.25,
                circles: Array.from({ length: 6 }, (_, idx) => ({
                    dx: (idx - 2.5) * (25 + Math.random() * 15),
                    dy: (Math.random() - 0.5) * 15,
                    r: 35 + Math.random() * 45
                }))
            });
        }

        // Light Raindrops
        const raindrops = [];
        const numRaindrops = 55;
        for (let i = 0; i < numRaindrops; i++) {
            raindrops.push({
                x: Math.random() * window.innerWidth,
                y: Math.random() * window.innerHeight,
                length: 10 + Math.random() * 12,
                speed: 6 + Math.random() * 5,
                opacity: 0.2 + Math.random() * 0.25,
                angle: 0.05 + Math.random() * 0.06 // gentle wind slant
            });
        }

        // Animated Drones
        const skyDrones = [];
        const numSkyDrones = 3;
        for (let i = 0; i < numSkyDrones; i++) {
            skyDrones.push({
                x: Math.random() * window.innerWidth,
                y: 100 + Math.random() * (window.innerHeight * 0.35),
                speedX: 0.4 + Math.random() * 0.6,
                speedY: 0,
                wobbleSpeed: 0.02 + Math.random() * 0.03,
                wobbleRange: 5 + Math.random() * 8,
                wobbleOffset: Math.random() * 100,
                scale: 0.35 + Math.random() * 0.35,
                propAngle: 0,
                color: ['#ff5500', '#0284c7', '#059669'][i % 3]
            });
        }

        const drawSkyDrone = (ctx, d, time) => {
            ctx.save();
            const wobble = Math.sin(time * d.wobbleSpeed + d.wobbleOffset) * d.wobbleRange;
            ctx.translate(d.x, d.y + wobble);
            ctx.scale(d.scale, d.scale);
            d.propAngle += 0.4;
            
            ctx.strokeStyle = '#0f172a';
            ctx.lineWidth = 4;
            ctx.beginPath();
            ctx.moveTo(-30, -18); ctx.lineTo(30, 18);
            ctx.moveTo(30, -18); ctx.lineTo(-30, 18);
            ctx.stroke();

            const motorPos = [
                { x: -30, y: -18 }, { x: 30, y: -18 },
                { x: -30, y: 18 }, { x: 30, y: 18 }
            ];
            motorPos.forEach(p => {
                ctx.fillStyle = '#1e293b';
                ctx.beginPath();
                ctx.arc(p.x, p.y, 5, 0, Math.PI * 2);
                ctx.fill();

                ctx.strokeStyle = 'rgba(255, 255, 255, 0.4)';
                ctx.lineWidth = 2.5;
                ctx.beginPath();
                const px = Math.cos(d.propAngle) * 15;
                const py = Math.sin(d.propAngle) * 4;
                ctx.moveTo(p.x - px, p.y - py);
                ctx.lineTo(p.x + px, p.y + py);
                ctx.stroke();
            });

            ctx.fillStyle = '#0f172a';
            ctx.beginPath();
            ctx.roundRect(-15, -6, 30, 12, 4);
            ctx.fill();

            ctx.fillStyle = d.color;
            ctx.beginPath();
            ctx.arc(0, -3, 10, 0, Math.PI, true);
            ctx.fill();

            const flash = Math.floor(time / 150) % 2 === 0;
            if (flash) {
                ctx.fillStyle = '#ef4444';
                ctx.beginPath();
                ctx.arc(0, 8, 3.5, 0, Math.PI * 2);
                ctx.fill();
                ctx.fillStyle = 'rgba(239, 68, 68, 0.5)';
                ctx.beginPath();
                ctx.arc(0, 8, 10, 0, Math.PI * 2);
                ctx.fill();
            }
            ctx.restore();
        };

        let skyFrameCount = 0;
        const animateSky = () => {
            skyFrameCount++;
            sCtx.clearRect(0, 0, skyCanvas.width, skyCanvas.height);

            // 1. Soft Light Clouds
            skyClouds.forEach(c => {
                c.circles.forEach(circle => {
                    const cx = c.x + circle.dx * c.scale;
                    const cy = c.y + circle.dy * c.scale;
                    const r = circle.r * c.scale;
                    const grad = sCtx.createRadialGradient(cx, cy, 0, cx, cy, r);
                    
                    // Misty white clouds
                    grad.addColorStop(0, `rgba(255, 255, 255, ${c.opacity})`);
                    grad.addColorStop(0.5, `rgba(255, 255, 255, ${c.opacity * 0.75})`);
                    grad.addColorStop(0.8, `rgba(255, 255, 255, ${c.opacity * 0.3})`);
                    grad.addColorStop(1, 'rgba(255, 255, 255, 0)');
                    sCtx.fillStyle = grad;
                    sCtx.beginPath();
                    sCtx.arc(cx, cy, r, 0, Math.PI * 2);
                    sCtx.fill();
                });
                c.x += c.speed;
                if (c.x > skyCanvas.width + 400) {
                    c.x = -400;
                    c.y = Math.random() * (skyCanvas.height * 0.45);
                }
            });

            // 2. Gentle Raindrops
            sCtx.lineWidth = 1.0;
            raindrops.forEach(r => {
                sCtx.strokeStyle = `rgba(255, 255, 255, ${r.opacity})`; // white light rain
                sCtx.beginPath();
                sCtx.moveTo(r.x, r.y);
                sCtx.lineTo(r.x + r.angle * r.length, r.y + r.length);
                sCtx.stroke();

                r.y += r.speed;
                r.x += r.angle * r.speed;

                if (r.y > skyCanvas.height) {
                    r.y = -20;
                    r.x = Math.random() * skyCanvas.width;
                }
            });

            // 3. Drones navigating
            skyDrones.forEach(d => {
                drawSkyDrone(sCtx, d, skyFrameCount * 16);
                d.x += d.speedX;
                if (d.x > skyCanvas.width + 150) {
                    d.x = -150;
                    d.y = 100 + Math.random() * (skyCanvas.height * 0.35);
                }
            });

            requestAnimationFrame(animateSky);
        };
        animateSky();
    };

    initSky();
});
