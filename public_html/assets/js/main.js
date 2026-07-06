(function () {
  'use strict';

  const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* -----------------------------------------------------------------------
     Mobile navigation
     ----------------------------------------------------------------------- */
  const navToggle = document.querySelector('[data-nav-toggle]');
  const siteNav = document.getElementById('site-nav');
  const navToggleLabel = document.querySelector('[data-nav-toggle-label]');

  if (navToggle && siteNav) {
    const openLabel = navToggleLabel?.textContent ?? '';
    const closeLabel = navToggle.getAttribute('data-close-label') ?? openLabel;

    navToggle.addEventListener('click', () => {
      const isOpen = siteNav.classList.toggle('is-open');
      navToggle.setAttribute('aria-expanded', String(isOpen));
      if (navToggleLabel) {
        navToggleLabel.textContent = isOpen ? closeLabel : openLabel;
      }
    });

    siteNav.querySelectorAll('a').forEach((link) => {
      link.addEventListener('click', () => {
        siteNav.classList.remove('is-open');
        navToggle.setAttribute('aria-expanded', 'false');
        if (navToggleLabel) {
          navToggleLabel.textContent = openLabel;
        }
      });
    });
  }

  /* -----------------------------------------------------------------------
     Header scroll state
     ----------------------------------------------------------------------- */
  const header = document.getElementById('site-header');

  if (header) {
    const onScroll = () => {
      header.classList.toggle('is-scrolled', window.scrollY > 8);
    };
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
  }

  /* -----------------------------------------------------------------------
     Active section highlighting
     ----------------------------------------------------------------------- */
  const navLinks = document.querySelectorAll('[data-nav-link]');
  const sections = [];

  navLinks.forEach((link) => {
    const id = link.getAttribute('data-nav-link');
    const section = document.getElementById(id);
    if (section) {
      sections.push({ id, el: section, link });
    }
  });

  if (sections.length > 0 && 'IntersectionObserver' in window) {
    const sectionObserver = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            const id = entry.target.id;
            navLinks.forEach((link) => {
              link.classList.toggle(
                'is-active',
                link.getAttribute('data-nav-link') === id
              );
            });
          }
        });
      },
      {
        rootMargin: '-40% 0px -50% 0px',
        threshold: 0,
      }
    );

    sections.forEach(({ el }) => sectionObserver.observe(el));
  }

  /* -----------------------------------------------------------------------
     Scroll reveal
     ----------------------------------------------------------------------- */
  const revealEls = document.querySelectorAll('.reveal');

  if (revealEls.length > 0) {
    if (prefersReducedMotion || !('IntersectionObserver' in window)) {
      revealEls.forEach((el) => el.classList.add('is-visible'));
    } else {
      const revealObserver = new IntersectionObserver(
        (entries, observer) => {
          entries.forEach((entry) => {
            if (entry.isIntersecting) {
              entry.target.classList.add('is-visible');
              observer.unobserve(entry.target);
            }
          });
        },
        { threshold: 0.12, rootMargin: '0px 0px -5% 0px' }
      );

      revealEls.forEach((el) => revealObserver.observe(el));
    }
  }

  /* -----------------------------------------------------------------------
     Contact form — client-side validation only
     ----------------------------------------------------------------------- */
  const contactForm = document.getElementById('contact-form');
  const formFeedback = document.getElementById('form-feedback');

  if (contactForm && formFeedback) {
    const successMessage = contactForm.getAttribute('data-success') ?? '';

    const showFeedback = (message, type) => {
      formFeedback.textContent = message;
      formFeedback.hidden = false;
      formFeedback.className = `form-feedback is-${type}`;
    };

    const clearInvalid = () => {
      contactForm.querySelectorAll('.is-invalid').forEach((el) => {
        el.classList.remove('is-invalid');
      });
    };

    contactForm.addEventListener('submit', (event) => {
      event.preventDefault();
      clearInvalid();
      formFeedback.hidden = true;

      const name = contactForm.querySelector('#contact-name');
      const email = contactForm.querySelector('#contact-email');
      const subject = contactForm.querySelector('#contact-subject');
      const message = contactForm.querySelector('#contact-message');

      let valid = true;

      [name, email, subject, message].forEach((field) => {
        if (!field || !field.value.trim()) {
          field?.classList.add('is-invalid');
          valid = false;
        }
      });

      if (email && email.value && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.value)) {
        email.classList.add('is-invalid');
        valid = false;
      }

      if (!valid) {
        showFeedback(
          contactForm.getAttribute('data-error') ?? '',
          'error'
        );
        return;
      }

      showFeedback(successMessage, 'success');
      contactForm.reset();
    });
  }
})();
