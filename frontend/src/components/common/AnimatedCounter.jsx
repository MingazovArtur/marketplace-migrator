import React, { useState, useEffect, useRef } from 'react';

const AnimatedCounter = ({ target, duration = 1000, className = '' }) => {
  const [current, setCurrent] = useState(0);
  const previousTarget = useRef(0);
  const animationRef = useRef(null);

  useEffect(() => {
    const start = previousTarget.current;
    const end = target;
    const startTime = performance.now();

    const animate = (currentTime) => {
      const elapsed = currentTime - startTime;
      const progress = Math.min(elapsed / duration, 1);

      // Easing function (ease-out)
      const easeOut = 1 - Math.pow(1 - progress, 3);
      const value = Math.floor(start + (end - start) * easeOut);

      setCurrent(value);

      if (progress < 1) {
        animationRef.current = requestAnimationFrame(animate);
      } else {
        previousTarget.current = end;
      }
    };

    animationRef.current = requestAnimationFrame(animate);

    return () => {
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current);
      }
    };
  }, [target, duration]);

  return <span className={className}>{current.toLocaleString('ru-RU')}</span>;
};

export default AnimatedCounter;
