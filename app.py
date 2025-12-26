    # --- STEP 2: CONFIGURE SERVICES ---
    elif st.session_state.stage == 2:
        st.header("Step 2: Service Details")
        st.info("Edit details below. Use the section below the table to Add or Remove dates.")
        
        # Ensure correct types for the editor
        if not st.session_state.roster_dates:
             # Fallback if empty
             st.session_state.roster_dates = []

        df_dates = pd.DataFrame(st.session_state.roster_dates)
        
        # Ensure 'Date' column is strictly date objects
        if not df_dates.empty and 'Date' in df_dates.columns:
            df_dates['Date'] = pd.to_datetime(df_dates['Date']).dt.date
        
        # EDITABLE TABLE
        edited_df = st.data_editor(
            df_dates,
            column_config={
                "Date": st.column_config.DateColumn("Service Date", format="DD-MMM", required=True),
                "Combined": st.column_config.CheckboxColumn("MSS Combined?", default=False),
                "HC": st.column_config.CheckboxColumn("Holy Communion?", default=False),
                "Notes": st.column_config.TextColumn("Notes (Optional)"),
            },
            num_rows="dynamic", # Allows simple row addition/deletion via keyboard too
            use_container_width=True,
            hide_index=True,
            key="date_editor"
        )
        
        # --- MANAGE DATES SECTION (Add / Remove) ---
        st.write("### Manage Dates")
        with st.container(border=True):
            tab_add, tab_remove = st.tabs(["➕ Add Date", "🗑️ Remove Date"])
            
            # --- TAB: ADD DATE ---
            with tab_add:
                c1, c2 = st.columns([1, 1])
                with c1:
                    new_date = st.date_input("Select Date to Add", key="add_picker")
                with c2:
                    st.write("") 
                    st.write("") 
                    if st.button("Add Date"):
                        # Capture current state of table so we don't lose checkmarks
                        current_data = edited_df.to_dict('records')
                        
                        # Validate
                        if any(d.get('Date') == new_date for d in current_data if d.get('Date')):
                            st.warning("That date is already in the list.")
                        else:
                            new_entry = {"Date": new_date, "Combined": False, "HC": False, "Notes": ""}
                            current_data.append(new_entry)
                            # Sort by date
                            current_data.sort(key=lambda x: x['Date'] if x.get('Date') else date.max)
                            st.session_state.roster_dates = current_data
                            st.rerun()

            # --- TAB: REMOVE DATE ---
            with tab_remove:
                # Get valid dates from current table state
                valid_dates = sorted([
                    d['Date'] for d in edited_df.to_dict('records') 
                    if d.get('Date') and isinstance(d['Date'], date)
                ])
                
                if valid_dates:
                    c1, c2 = st.columns([1, 1])
                    with c1:
                        date_to_remove = st.selectbox(
                            "Select Date to Remove", 
                            valid_dates, 
                            format_func=lambda x: x.strftime("%d-%b-%Y")
                        )
                    with c2:
                        st.write("")
                        st.write("")
                        if st.button("Delete Selected Date", type="primary"):
                            # Capture current table state
                            current_data = edited_df.to_dict('records')
                            
                            # Filter out the selected date
                            updated_data = [
                                row for row in current_data 
                                if row.get('Date') != date_to_remove
                            ]
                            
                            st.session_state.roster_dates = updated_data
                            st.rerun()
                else:
                    st.info("No dates available to remove.")

        st.markdown("---")
        
        # NAVIGATION
        col_l, col_r = st.columns([1, 5])
        if col_l.button("← Back"):
            st.session_state.stage = 1
            st.rerun()
            
        if col_r.button("Next: Availability →"):
            # Clean up: Remove rows where Date is None/Empty
            cleaned_rows = []
            for r in edited_df.to_dict('records'):
                if r.get('Date') and pd.notnull(r['Date']):
                    # Ensure python date object
                    if isinstance(r['Date'], pd.Timestamp):
                        r['Date'] = r['Date'].date()
                    cleaned_rows.append(r)
            
            # Final Sort
            cleaned_rows.sort(key=lambda x: x['Date'])
            
            st.session_state.roster_dates = cleaned_rows
            st.session_state.stage = 3
            st.rerun()
