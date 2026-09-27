'use strict';
// Small, progressively enhanced controls: no framework, no remote assets.
(() => {
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
  const controls = [];
  let opened = null;
  function reveal(element) {
    if (reduced.matches || !element.animate) return;
    element.getAnimations().forEach(animation => animation.cancel());
    element.animate([{opacity:0,transform:'translateY(7px)'},{opacity:1,transform:'translateY(0)'}],
      {duration:300,easing:'cubic-bezier(.2,.75,.25,1)'});
  }
  function sync() { controls.forEach(control => control.sync()); }
  for (const id of ['source','target','pauseSeconds']) {
    const select = document.getElementById(id);
    // Each enhanced combobox has its own accessible name. Avoid placing both
    // the native select and the replacement button inside one HTML label.
    if(select.parentElement.tagName==='LABEL'){
      const label=select.parentElement,field=document.createElement('div');
      field.className=id==='pauseSeconds'?'pause-field':'language-field';
      while(label.firstChild)field.append(label.firstChild);
      label.replaceWith(field);
    }
    // The native select remains the data source for the translation code.
    const wrap = document.createElement('div'); wrap.className='select-control';
    const trigger = document.createElement('button'); trigger.type='button';
    trigger.className='select-trigger'; trigger.setAttribute('role','combobox');
    trigger.setAttribute('aria-haspopup','listbox'); trigger.setAttribute('aria-expanded','false');
    trigger.setAttribute('aria-label',select.getAttribute('aria-label'));
    const menu = document.createElement('ul');menu.className='select-menu';menu.id=id+'-options';
    menu.setAttribute('role','listbox');menu.setAttribute('aria-label',select.getAttribute('aria-label'));
    menu.inert=true;trigger.setAttribute('aria-controls',menu.id);
    let focused=select.selectedIndex, search='',searchTimer;
    const options=Array.from(select.options).map((option,index)=>{
      const item=document.createElement('li');item.setAttribute('role','option');
      item.id=id+'-option-'+index;item.textContent=option.textContent;
      item.addEventListener('pointerdown',event=>event.preventDefault());
      item.addEventListener('click',()=>choose(index));menu.append(item);return item;
    });
    const control={
      sync(){trigger.textContent=select.selectedOptions[0].textContent;trigger.disabled=select.disabled;
        options.forEach((item,index)=>item.setAttribute('aria-selected',String(index===select.selectedIndex)));
        if(select.disabled)close();},close
    };
    function focusOption(index){focused=(index+options.length)%options.length;
      options.forEach((item,i)=>item.classList.toggle('is-focused',i===focused));
      trigger.setAttribute('aria-activedescendant',options[focused].id);
    }
    function open(){if(select.disabled)return;if(opened&&opened!==control)opened.close();
      control.sync();menu.inert=false;wrap.classList.add('is-open');trigger.setAttribute('aria-expanded','true');
      opened=control;focusOption(select.selectedIndex);
    }
    function close(){wrap.classList.remove('is-open');menu.inert=true;trigger.setAttribute('aria-expanded','false');
      trigger.removeAttribute('aria-activedescendant');if(opened===control)opened=null;
    }
    function choose(index){select.selectedIndex=index;close();control.sync();
      select.dispatchEvent(new Event('change',{bubbles:true}));trigger.focus();
    }
    trigger.addEventListener('click',()=>opened===control?close():open());
    trigger.addEventListener('keydown',event=>{
      const isOpen=opened===control;
      if(['ArrowDown','ArrowUp','Home','End','Enter',' ','Escape'].includes(event.key)){
        event.preventDefault();
        if(event.key==='Escape'){close();return;}
        if(event.key==='Enter'||event.key===' '){isOpen?choose(focused):open();return;}
        if(!isOpen)open();
        if(event.key==='Home')focusOption(0);
        else if(event.key==='End')focusOption(options.length-1);
        else if(isOpen)focusOption(focused+(event.key==='ArrowDown'?1:-1));
      }else if(event.key==='Tab')close();
      else if(event.key.length===1&&!event.ctrlKey&&!event.metaKey&&!event.altKey){
        clearTimeout(searchTimer);search+=event.key.toLowerCase();searchTimer=setTimeout(()=>search='',600);
        const index=Array.from(select.options).findIndex(option=>option.text.toLowerCase().startsWith(search));
        if(index>=0){if(!isOpen)open();focusOption(index);}
      }
    });
    select.after(wrap);wrap.append(trigger,menu);select.classList.add('select-native');
    select.tabIndex=-1;select.setAttribute('aria-hidden','true');
    select.addEventListener('change',()=>control.sync());
    new MutationObserver(()=>control.sync()).observe(select,{attributes:true,attributeFilter:['disabled']});
    control.sync();controls.push(control);
  }
  document.addEventListener('pointerdown',event=>{if(!event.target.closest('.select-control'))opened?.close();});
  document.addEventListener('focusin',event=>{if(!event.target.closest('.select-control'))opened?.close();});

  const settings=document.querySelector('.voice-settings');const summary=settings.querySelector('summary');
  let expanded=settings.open,animation=null;
  function setSettings(open){
    expanded=open;
    const start=settings.getBoundingClientRect().height;
    animation?.cancel();
    if(reduced.matches||!settings.animate){settings.open=open;return;}
    if(open)settings.open=true;
    const end=open?settings.getBoundingClientRect().height:summary.getBoundingClientRect().height+2;
    animation=settings.animate([{height:start+'px'},{height:end+'px'}],
      {duration:260,easing:'cubic-bezier(.2,.75,.25,1)'});
    animation.onfinish=()=>{settings.open=expanded;animation=null;};
  }
  summary.addEventListener('click',event=>{event.preventDefault();setSettings(!expanded);});
  window.JTUI={reveal,sync,openSettings(){setSettings(true);}};
})();
